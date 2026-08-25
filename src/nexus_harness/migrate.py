from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from nexus_harness.inventory import InventoryReport, scan_tree

SKIP_ROOT_PARTS = frozenset({"inputs", "legacy", ".git"})
CANONICAL_PREFIXES = ("core/", "skills/", "upstream/", "src/", "tests/")
GENERATED_SKILL_PREFIXES = (
    "agents-skills/",
    "claude/skills/",
    "cursor/skills/",
    "codex/skills/",
    "dist/",
)
ARCHIVE_NAME = "nexus-harness-export-20260825-094238.tar.gz"


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_skipped(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    return bool(relative.parts) and relative.parts[0] in SKIP_ROOT_PARTS


def _is_canonical(relative: str) -> bool:
    return any(
        relative == prefix.rstrip("/") or relative.startswith(prefix)
        for prefix in CANONICAL_PREFIXES
    )


def _is_generated_skill(relative: str) -> bool:
    return any(relative.startswith(prefix) for prefix in GENERATED_SKILL_PREFIXES)


def _is_harness_sync_stale(relative: str, path: Path) -> bool:
    if not relative.startswith("harness-sync/"):
        return False
    name = path.name.lower()
    if name.endswith(".log"):
        return True
    if "circuit-breaker" in name:
        return True
    if name != "status.json":
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    reason = str(payload.get("reason", "")).lower()
    status = str(payload.get("status", "")).lower()
    return "circuit-breaker" in reason or status == "blocked"


def _add_action(
    actions: list[dict],
    seen: set[str],
    relative: str,
    reason: str,
) -> None:
    if relative in seen:
        return
    seen.add(relative)
    actions.append({"action": "delete", "path": relative, "reason": reason})


def cleanup_plan(root: Path) -> list[dict]:
    root = Path(root)
    actions: list[dict] = []
    seen: set[str] = set()
    files = sorted(path for path in root.rglob("*") if path.is_file())

    for path in files:
        if _is_skipped(root, path):
            continue
        relative = _relative(root, path)
        if path.name.startswith("._"):
            _add_action(actions, seen, relative, "appledouble")
            continue
        if path.name.endswith(".bak") or path.suffix == ".bak":
            _add_action(actions, seen, relative, "bak")
            continue
        if _is_harness_sync_stale(relative, path):
            _add_action(actions, seen, relative, "harness-sync")

    skill_files = [
        path
        for path in files
        if path.name == "SKILL.md"
        and not _is_skipped(root, path)
        and not any(part.startswith("._") for part in path.parts)
    ]
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in skill_files:
        groups[sha256(path.read_bytes()).hexdigest()].append(path)

    for group in groups.values():
        if len(group) < 2:
            continue
        relatives = sorted(_relative(root, path) for path in group)
        keepers = [relative for relative in relatives if _is_canonical(relative)]
        if not keepers:
            generated = [
                relative for relative in relatives if _is_generated_skill(relative)
            ]
            if generated:
                keepers = [generated[0]]
            else:
                continue
        keep = set(keepers)
        for relative in relatives:
            if relative in keep or not _is_generated_skill(relative):
                continue
            _add_action(actions, seen, relative, "generated-skill-copy")

    return sorted(actions, key=lambda item: item["path"])


def _resolved_target(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    raw = Path(candidate)
    if raw.is_absolute():
        resolved = raw.resolve(strict=False)
    else:
        if ".." in raw.parts:
            raise ValueError(f"Cleanup path is outside the supplied root: {candidate}")
        resolved = (root / raw).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"Cleanup path is outside the supplied root: {candidate}"
        ) from error
    return resolved


def apply_cleanup(plan: list[dict], root: Path) -> None:
    root = Path(root)
    for item in plan:
        if item.get("action") != "delete":
            continue
        target = _resolved_target(root, Path(item["path"]))
        if target.is_file() or target.is_symlink():
            target.unlink()


def _inventory_payload(report: InventoryReport) -> dict[str, int]:
    return {
        "appledouble_count": report.appledouble_count,
        "duplicate_file_count": report.duplicate_file_count,
        "file_count": report.file_count,
        "redundant_bytes": report.redundant_bytes,
        "total_bytes": report.total_bytes,
    }


def _assert_report_paths(payload: dict) -> None:
    blob = json.dumps(payload, sort_keys=True)
    if ARCHIVE_NAME in blob:
        raise ValueError("cleanup report must not mention the immutable archive")
    for item in payload.get("would_clean", []):
        path = str(item.get("path", ""))
        if _is_canonical(path):
            raise ValueError(f"cleanup report must not delete canonical path: {path}")


def generate_cleanup_report(
    v4_root: Path,
    extract_root: Path,
    destination: Path,
    *,
    apply_tempfile: bool = True,
) -> dict:
    v4_root = Path(v4_root)
    extract_root = Path(extract_root)
    v4_plan = cleanup_plan(v4_root)
    would_clean = cleanup_plan(extract_root)

    tempfile_applied = False
    before = _inventory_payload(scan_tree(extract_root))
    after = before
    if apply_tempfile:
        with tempfile.TemporaryDirectory() as tmp:
            copy_root = Path(tmp) / "extract"
            shutil.copytree(extract_root, copy_root, symlinks=True)
            before = _inventory_payload(scan_tree(copy_root))
            apply_cleanup(cleanup_plan(copy_root), copy_root)
            after = _inventory_payload(scan_tree(copy_root))
            tempfile_applied = True

    payload = {
        "after": after,
        "applied_to": "tempfile-copy-of-extract" if tempfile_applied else None,
        "before": before,
        "dry_run": True,
        "planned_delete_count": len(would_clean),
        "v4_working_copy_apply": "no-op" if not v4_plan else "planned",
        "v4_working_copy_planned_deletes": v4_plan,
        "would_clean": would_clean,
    }
    if v4_plan:
        raise ValueError(
            "v4 working copy produced cleanup targets; inspect before applying"
        )
    _assert_report_paths(payload)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan and report v3 artifact cleanup")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--extract", type=Path, default=Path("legacy/v3-export"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/migration/cleanup-report.json"),
    )
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument(
        "--apply-tempfile",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args(argv)
    generate_cleanup_report(
        args.root,
        args.extract,
        args.report,
        apply_tempfile=args.apply_tempfile,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
