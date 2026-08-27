"""Before/after migration evidence against the frozen v3 export."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
from typing import Any

from nexus_harness.validate import CANONICAL_TREES

EXPECTED_ARCHIVE_SHA256 = (
    "cfa547d0b27b149ba0350783da965a550f754d484ac39b0b5e9e7a5951b7b1a0"
)
ARCHIVE_NAME = "nexus-harness-export-20260825-094238.tar.gz"
AFTER_TREES = CANONICAL_TREES + ("dist",)
SKIP_PARTS = frozenset({"__pycache__", ".git"})
GENERATED_PREFIXES = ("dist/", "tests/golden/")
HEURISTIC_RESOLVED = (
    "PRESERVED",
    "PRESERVE",
    "ALREADY_COVERED",
    "ALREADY COVERED",
    "DISCARDED_WITH_REASON",
    "DISCARD",
)

ADDITION_MARKERS: dict[str, tuple[str, ...]] = {
    "security_cleanup": (
        "src/nexus_harness/security.py",
        "src/nexus_harness/pretool.py",
        "src/nexus_harness/command.py",
        "core/security/policy.toml",
        "core/security/infrastructure.toml",
        "core/policies/production.toml",
        "core/policies/filesystem.toml",
        "core/policies/network.toml",
    ),
    "runtime_adapters": (
        "src/nexus_harness/adapters.py",
        "src/nexus_harness/runtime_claude.py",
        "src/nexus_harness/runtime_cursor.py",
        "src/nexus_harness/runtime_codex.py",
        "src/nexus_harness/compile.py",
    ),
    "memory": (
        "src/nexus_harness/memory/capsule.py",
        "src/nexus_harness/memory/store.py",
        "src/nexus_harness/memory/session.py",
        "core/memory/retrieval-policy.toml",
        "core/memory/memory-policy.toml",
        "core/memory/memory-record.schema.json",
    ),
    "ci": (
        "src/nexus_harness/ci.py",
        "src/nexus_harness/affected.py",
        "src/nexus_harness/build.py",
        "core/ci/profile.schema.json",
        "core/ci/deploy-manifest.schema.json",
    ),
    "github": (
        "src/nexus_harness/github.py",
        "src/nexus_harness/hierarchy.py",
        "src/nexus_harness/tracking.py",
        "src/nexus_harness/pull_request.py",
        "core/project/issue-contract.md",
        "core/project/pr-contract.md",
    ),
    "frontend": (
        "src/nexus_harness/visual.py",
        "src/nexus_harness/playwright.py",
        "src/nexus_harness/frontend_review.py",
        "skills/nexus-frontend/SKILL.md",
        "core/quality/frontend.toml",
        "core/quality/visual-evidence.schema.json",
    ),
    "posthog": (
        "src/nexus_harness/posthog.py",
        "src/nexus_harness/incidents.py",
        "src/nexus_harness/incident_policy.py",
        "core/observability/posthog.toml",
        "core/observability/incidents.toml",
    ),
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_archive(root: Path) -> Path | None:
    candidates = (
        root / ARCHIVE_NAME,
        root / "inputs" / ARCHIVE_NAME,
        root / "legacy" / ARCHIVE_NAME,
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _archive_identity(
    root: Path,
    baseline: dict[str, Any],
    expected_archive_sha256: str,
) -> dict[str, Any]:
    frozen = str(baseline.get("source_archive_sha256") or "")
    archive = _find_archive(root)
    if archive is None:
        limitation = (
            f"Original archive {ARCHIVE_NAME} is unavailable in this worktree. "
            "SHA is taken from frozen docs/migration/v3-baseline.json; "
            "current SHA was not computed."
        )
        return {
            "archive_present": False,
            "archive_path": None,
            "source_archive_sha256": frozen,
            "source_archive_sha_source": "frozen-baseline",
            "archive_limitation": limitation,
            "archive_unchanged": bool(frozen) and frozen == expected_archive_sha256,
            "expected_archive_sha256": expected_archive_sha256,
        }
    computed = _sha256_file(archive)
    return {
        "archive_present": True,
        "archive_path": archive.relative_to(root).as_posix(),
        "source_archive_sha256": computed,
        "source_archive_sha_source": "computed",
        "archive_limitation": None,
        "archive_unchanged": computed == expected_archive_sha256,
        "expected_archive_sha256": expected_archive_sha256,
    }


def _skip_file(path: Path) -> bool:
    if path.name in {".DS_Store", ".gitkeep"}:
        return True
    if path.name.startswith("._") or path.suffix in {".pyc", ".pyo"}:
        return True
    return any(part in SKIP_PARTS or part.startswith("._") for part in path.parts)


def _is_generated_relative(relative: str) -> bool:
    return any(relative.startswith(prefix) for prefix in GENERATED_PREFIXES)


def _scan_after(root: Path) -> dict[str, int]:
    hashes: dict[str, list[tuple[str, int]]] = {}
    files = 0
    total_bytes = 0
    for tree in AFTER_TREES:
        base = root / tree
        if not base.is_dir():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            if _skip_file(path):
                continue
            data = path.read_bytes()
            relative = path.relative_to(root).as_posix()
            digest = sha256(data).hexdigest()
            hashes.setdefault(digest, []).append((relative, len(data)))
            files += 1
            total_bytes += len(data)

    duplicate_count = 0
    redundant_bytes = 0
    generated_duplicate_count = 0
    generated_redundant_bytes = 0
    maintained_duplicate_count = 0
    maintained_redundant_bytes = 0
    for group in hashes.values():
        if len(group) < 2:
            continue
        extras = group[1:]
        duplicate_count += len(extras)
        redundant_bytes += sum(size for _, size in extras)
        for relative, size in extras:
            if _is_generated_relative(relative):
                generated_duplicate_count += 1
                generated_redundant_bytes += size
            else:
                maintained_duplicate_count += 1
                maintained_redundant_bytes += size

    return {
        "file_count": files,
        "duplicate_file_count": duplicate_count,
        "redundant_bytes": redundant_bytes,
        "total_bytes": total_bytes,
        "generated_duplicate_count": generated_duplicate_count,
        "generated_redundant_bytes": generated_redundant_bytes,
        "maintained_duplicate_count": maintained_duplicate_count,
        "maintained_redundant_bytes": maintained_redundant_bytes,
    }


def _inventory_fields(payload: dict[str, Any]) -> dict[str, int]:
    return {
        "file_count": int(payload["file_count"]),
        "duplicate_file_count": int(payload["duplicate_file_count"]),
        "redundant_bytes": int(payload["redundant_bytes"]),
        "total_bytes": int(payload.get("total_bytes") or 0),
    }


def _canonical_skills(root: Path) -> list[str]:
    skills_root = root / "skills"
    if not skills_root.is_dir():
        return []
    names = []
    for path in sorted(skills_root.glob("*/SKILL.md")):
        if path.is_file():
            names.append(path.parent.name)
    return names


def _parse_removed_config_classes(text: str) -> list[str]:
    lines = text.splitlines()
    capturing = False
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            capturing = stripped == "## Remove from global configuration"
            continue
        if capturing and stripped.startswith("- "):
            items.append(stripped[2:].rstrip(".").replace("`", "").strip())
    return items


def _existing_paths(root: Path, relatives: Iterable[str]) -> list[str]:
    found = []
    for relative in relatives:
        if (root / relative).exists():
            found.append(relative)
    return found


def _heuristic_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= {"-"}:
            continue
        if cells[0].lower() in {"source"}:
            continue
        rows.append(
            {
                "source": cells[0],
                "relationship": cells[1],
                "status": cells[-1],
            }
        )
    return rows


def _unresolved_divergent(ledger: list[dict[str, Any]], heuristics_text: str) -> int:
    unresolved: set[str] = set()
    for entry in ledger:
        if entry.get("relationship") == "divergent" and not entry.get("decision"):
            unresolved.add(str(entry.get("name") or ""))
    if "## Pending extract" in heuristics_text:
        unresolved.add("pending-extract")
    for row in _heuristic_rows(heuristics_text):
        status = row["status"]
        if not any(status.startswith(token) for token in HEURISTIC_RESOLVED):
            unresolved.add(row["source"])
    unresolved.discard("")
    return len(unresolved)


def _debt_groups(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    resolved: list[str] = []
    accepted: list[str] = []
    unresolved: list[str] = []
    for item in items:
        ident = str(item.get("id") or "")
        status = str(item.get("status") or "")
        if status == "resolved":
            resolved.append(ident)
        elif status == "accepted_residual":
            accepted.append(ident)
        else:
            unresolved.append(ident)
    return {
        "resolved": resolved,
        "accepted_residual": accepted,
        "unresolved": unresolved,
    }


def _generated_counts(root: Path) -> tuple[int, int]:
    lock_path = root / "harness.lock"
    locked = 0
    if lock_path.is_file():
        lock = _load_json(lock_path)
        generated = lock.get("generated_hashes") or {}
        engine = lock.get("engine_hashes") or {}
        locked = len(generated) + len(engine)
    dist = root / "dist"
    materialized = 0
    if dist.is_dir():
        materialized = sum(
            1 for path in dist.rglob("*") if path.is_file() and not _skip_file(path)
        )
    return locked, materialized


def build_migration_report(
    root: Path,
    *,
    expected_archive_sha256: str = EXPECTED_ARCHIVE_SHA256,
) -> dict[str, Any]:
    root = Path(root)
    baseline = _load_json(root / "docs/migration/v3-baseline.json")
    cleanup = _load_json(root / "docs/migration/cleanup-report.json")
    ledger = _load_json(root / "docs/migration/skill-ledger.json")
    debt_doc = _load_json(root / "docs/migration/debt.json")
    heuristics_text = (root / "docs/migration/unique-heuristics.md").read_text(
        encoding="utf-8"
    )
    migration_map = (root / "docs/MIGRATION-MAP.md").read_text(encoding="utf-8")

    identity = _archive_identity(root, baseline, expected_archive_sha256)
    after = _scan_after(root)
    canonical = _canonical_skills(root)
    ledger_sorted = sorted(ledger, key=lambda item: str(item.get("name") or ""))
    divergent = [
        item for item in ledger_sorted if item.get("relationship") == "divergent"
    ]
    generated_artifacts_count, materialized_generated_count = _generated_counts(root)
    additions = {
        name: _existing_paths(root, paths) for name, paths in ADDITION_MARKERS.items()
    }

    report: dict[str, Any] = {
        **identity,
        "before": _inventory_fields(baseline),
        "cleanup_after": _inventory_fields(cleanup.get("after") or cleanup),
        "after": after,
        "after_scope": list(AFTER_TREES),
        "canonical_skills": canonical,
        "canonical_skill_count": len(canonical),
        "generated_artifacts_count": generated_artifacts_count,
        "materialized_generated_count": materialized_generated_count,
        "removed_global_project_specific_config_classes": _parse_removed_config_classes(
            migration_map
        ),
        "skill_ledger_decisions": ledger_sorted,
        "divergent_skill_decisions": divergent,
        "unresolved_divergent_skill_decisions": _unresolved_divergent(
            ledger_sorted, heuristics_text
        ),
        "unique_heuristics": _heuristic_rows(heuristics_text),
        "debt": _debt_groups(list(debt_doc.get("items") or [])),
        **additions,
    }
    return report


def render_migration_report(report: dict[str, Any]) -> str:
    before = report["before"]
    after = report["after"]
    cleanup = report["cleanup_after"]
    limitation = report.get("archive_limitation")
    lines = [
        "# Nexus Harness v4 — Final migration report",
        "",
        "Numbers below are derived from `docs/migration/v3-baseline.json`,",
        "`docs/migration/cleanup-report.json`, `docs/migration/skill-ledger.json`,",
        "`docs/migration/debt.json`, `docs/migration/unique-heuristics.md`,",
        "`docs/MIGRATION-MAP.md`, `harness.lock`, and a scan of the canonical",
        "v4 trees plus `dist/`. No counts were invented.",
        "",
        "## Source archive",
        "",
        f"- Expected SHA-256: `{report['expected_archive_sha256']}`",
        f"- Recorded SHA-256: `{report['source_archive_sha256']}`",
        f"- SHA source: {report['source_archive_sha_source']}",
        f"- Archive present: {'yes' if report['archive_present'] else 'no'}",
        f"- Archive path: `{report['archive_path'] or 'n/a'}`",
        f"- Archive unchanged: {'yes' if report['archive_unchanged'] else 'no'}",
    ]
    if limitation:
        lines.extend(["- Limitation: " + limitation])
    lines.extend(
        [
            "",
            "## File inventory",
            "",
            "| Snapshot | Files | Duplicate files | Redundant bytes | Total bytes |",
            "| --- | ---: | ---: | ---: | ---: |",
            (
                f"| v3 baseline | {before['file_count']} | "
                f"{before['duplicate_file_count']} | {before['redundant_bytes']} | "
                f"{before['total_bytes']} |"
            ),
            (
                f"| v3 cleanup (tempfile extract) | {cleanup['file_count']} | "
                f"{cleanup['duplicate_file_count']} | {cleanup['redundant_bytes']} | "
                f"{cleanup['total_bytes']} |"
            ),
            (
                f"| v4 canonical + dist | {after['file_count']} | "
                f"{after['duplicate_file_count']} | {after['redundant_bytes']} | "
                f"{after['total_bytes']} |"
            ),
            "",
            "v4 after-scope: `" + ", ".join(report["after_scope"]) + "`.",
            "",
            "Duplicate extras in the v4 scan are split into intentional generated",
            "repetition (`dist/`, `tests/golden/`) versus manually maintained copies:",
            "",
            (
                f"- generated duplicate count/bytes: "
                f"{after['generated_duplicate_count']} / "
                f"{after['generated_redundant_bytes']}"
            ),
            (
                f"- maintained duplicate count/bytes: "
                f"{after['maintained_duplicate_count']} / "
                f"{after['maintained_redundant_bytes']}"
            ),
            (
                f"- generated artifacts (lock generated_hashes + engine_hashes): "
                f"{report['generated_artifacts_count']}"
            ),
            (
                f"- materialized dist files (excluding .gitkeep): "
                f"{report['materialized_generated_count']}"
            ),
            "",
            "## Canonical skills",
            "",
            f"- canonical skill count: {report['canonical_skill_count']}",
        ]
    )
    for name in report["canonical_skills"]:
        lines.append(f"- `{name}`")
    lines.extend(
        [
            "",
            "## Removed global project-specific configuration",
            "",
        ]
    )
    for item in report["removed_global_project_specific_config_classes"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Divergent skill decisions",
            "",
            (
                "Unresolved divergent-skill decisions: "
                f"{report['unresolved_divergent_skill_decisions']}"
            ),
            "",
        ]
    )
    for item in report["divergent_skill_decisions"]:
        target = item.get("target") or "none"
        lines.append(
            f"- `{item['name']}`: {item.get('decision')} "
            f"→ `{target}` "
            f"({item.get('rationale') or 'ledger decision recorded'})"
        )
    lines.extend(["", "## Skill ledger (every semantic decision)", ""])
    for item in report["skill_ledger_decisions"]:
        target = item.get("target") or "none"
        lines.append(
            f"- `{item['name']}`: {item.get('decision')} / "
            f"{item.get('relationship')} → `{target}`"
        )
    lines.extend(["", "## Unique heuristics", ""])
    for row in report["unique_heuristics"]:
        lines.append(f"- {row['source']} ({row['relationship']}): {row['status']}")
    debt = report["debt"]
    lines.extend(
        [
            "",
            "## Debt",
            "",
            "- resolved: " + ", ".join(debt["resolved"])
            if debt["resolved"]
            else "- resolved: none",
            (
                "- accepted residual: " + ", ".join(debt["accepted_residual"])
                if debt["accepted_residual"]
                else "- accepted residual: none"
            ),
            (
                "- unresolved: " + ", ".join(debt["unresolved"])
                if debt["unresolved"]
                else "- unresolved: none"
            ),
            "",
            "## Security cleanup",
            "",
        ]
    )
    for path in report["security_cleanup"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## Runtime adapters", ""])
    for path in report["runtime_adapters"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## Memory", ""])
    for path in report["memory"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## CI", ""])
    for path in report["ci"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## GitHub", ""])
    for path in report["github"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## Frontend", ""])
    for path in report["frontend"]:
        lines.append(f"- `{path}`")
    lines.extend(["", "## PostHog", ""])
    for path in report["posthog"]:
        lines.append(f"- `{path}`")
    lines.append("")
    return "\n".join(lines)


def write_migration_report(
    root: Path, destination: Path | None = None
) -> dict[str, Any]:
    root = Path(root)
    report = build_migration_report(root)
    output = (
        Path(destination) if destination else root / "docs/migration/final-report.md"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_migration_report(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the v4 migration report")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/migration/final-report.md"),
    )
    args = parser.parse_args(argv)
    root = args.root
    output = args.output
    if not output.is_absolute():
        output = root / output
    write_migration_report(root, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
