from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from nexus_harness.lockfile import build_lock

CANONICAL_SKILL_NAMES = frozenset(
    {
        "accessibility",
        "nexus-frontend",
        "nexus-handoff",
        "nexus-quality",
        "nexus-ship",
        "nexus-verify",
        "nexus-workflow",
    }
)
CANONICAL_TREES = ("core", "skills", "profiles", "src", "tests", "upstream")
PARSE_TREES = ("core", "skills", "profiles", "src", "tests")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
SSH_TARGET = re.compile(
    r"(?i)(?:\b(?:ssh|scp)://|\b[A-Za-z0-9._-]+@(?:[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\d{1,3}(?:\.\d{1,3}){3})\b)"
)
ABS_CLIENT_PATH = re.compile(
    r"(?:/Users/[^\s\"']+|/home/[^\s\"']+|[A-Za-z]:\\[^\s\"']+)"
)
MODEL_PATTERNS = (
    re.compile(r"(?i)\bclaude-sonnet\b"),
    re.compile(r"(?i)\bclaude-opus\b"),
    re.compile(r"(?i)\bclaude-haiku\b"),
    re.compile(r"(?i)\bgpt-4\b"),
    re.compile(r"(?i)\bgpt-5\b"),
    re.compile(r"(?i)\bgpt-3\.5\b"),
    re.compile(r"(?i)\bkimi-k[0-9]\b"),
    re.compile(r"(?i)\bcursor-grok\b"),
    re.compile(r"(?i)\bgrok-4\b"),
    re.compile(r"(?i)\bcomposer-2\b"),
    re.compile(r"(?i)\bgemini-[0-9]\b"),
    re.compile(r"(?i)\bo1-preview\b"),
    re.compile(r"(?i)\bo3-mini\b"),
    re.compile(r"(?i)\bsonnet\b"),
    re.compile(r"(?i)\bopus\b"),
    re.compile(r"(?i)\bhaiku\b"),
)
TEXT_SUFFIXES = {".toml", ".json", ".md", ".txt"}


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]


def _is_frozen(relative: str) -> bool:
    return (
        relative in {"inputs", "legacy", "docs/_bundle"}
        or relative.startswith("inputs/")
        or relative.startswith("legacy/")
        or relative.startswith("docs/_bundle/")
    )


def _is_project_override(relative: str) -> bool:
    return relative == "profiles/projects" or relative.startswith("profiles/projects/")


def _is_appledouble(path: Path) -> bool:
    return path.name.startswith("._") or any(
        part.startswith("._") for part in path.parts
    )


def _is_bak(path: Path) -> bool:
    return path.name.endswith(".bak") or path.suffix == ".bak"


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_tree_files(root: Path, directory: str):
    tree = root / directory
    if not tree.is_dir():
        return
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        yield path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _check_parseable(root: Path, errors: list[str]) -> None:
    candidates: list[Path] = []
    for directory in PARSE_TREES:
        candidates.extend(_iter_tree_files(root, directory))
    lock = root / "harness.lock"
    if lock.is_file():
        candidates.append(lock)
    vendor = root / "upstream" / "vendor-lock.json"
    if vendor.is_file():
        candidates.append(vendor)

    seen: set[str] = set()
    for path in candidates:
        relative = _relative(root, path)
        if relative in seen or _is_frozen(relative) or _is_appledouble(path):
            continue
        seen.add(relative)
        if path.suffix == ".toml":
            try:
                with path.open("rb") as handle:
                    tomllib.load(handle)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                errors.append(f"unparseable TOML: {relative} ({exc})")
        elif path.suffix == ".json" or path.name == "harness.lock":
            try:
                json.loads(_read_text(path))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"unparseable JSON: {relative} ({exc})")


def _check_skills(root: Path, errors: list[str]) -> None:
    skills_root = root / "skills"
    expected = {f"skills/{name}/SKILL.md" for name in CANONICAL_SKILL_NAMES}
    if not skills_root.is_dir():
        errors.append(
            "canonical skills must be exactly one SKILL.md each for: "
            + ", ".join(sorted(CANONICAL_SKILL_NAMES))
        )
        return
    found = {
        _relative(root, path)
        for path in skills_root.rglob("SKILL.md")
        if path.is_file() and not _is_appledouble(path)
    }
    if found != expected:
        errors.append(
            "canonical skills must be exactly one SKILL.md each for: "
            + ", ".join(sorted(CANONICAL_SKILL_NAMES))
        )


def _check_appledouble_bak(root: Path, errors: list[str]) -> None:
    for directory in CANONICAL_TREES:
        for path in _iter_tree_files(root, directory):
            relative = _relative(root, path)
            if _is_frozen(relative):
                continue
            if _is_appledouble(path):
                errors.append(f"appledouble: {relative}")
            elif _is_bak(path):
                errors.append(f"bak: {relative}")


def _check_absolute_paths(root: Path, errors: list[str]) -> None:
    for directory in ("core", "profiles"):
        for path in _iter_tree_files(root, directory):
            relative = _relative(root, path)
            if (
                _is_frozen(relative)
                or _is_project_override(relative)
                or _is_appledouble(path)
                or path.suffix not in TEXT_SUFFIXES
            ):
                continue
            text = _read_text(path)
            match = ABS_CLIENT_PATH.search(text)
            if match:
                errors.append(
                    f"absolute client/project path in {relative}: {match.group(0)}"
                )


def _check_production_targets(root: Path, errors: list[str]) -> None:
    for path in _iter_tree_files(root, "core"):
        relative = _relative(root, path)
        if (
            _is_frozen(relative)
            or _is_appledouble(path)
            or path.suffix not in TEXT_SUFFIXES
        ):
            continue
        text = _read_text(path)
        ip_match = IPV4.search(text)
        if ip_match:
            errors.append(
                f"IP/SSH production target in {relative}: {ip_match.group(0)}"
            )
            continue
        ssh_match = SSH_TARGET.search(text)
        if ssh_match:
            errors.append(
                f"IP/SSH production target in {relative}: {ssh_match.group(0)}"
            )


def _check_constitution_models(root: Path, errors: list[str]) -> None:
    constitution = root / "core" / "constitution.md"
    if not constitution.is_file():
        errors.append("missing core/constitution.md")
        return
    text = _read_text(constitution)
    for pattern in MODEL_PATTERNS:
        match = pattern.search(text)
        if match:
            errors.append(f"model name in core/constitution.md: {match.group(0)}")
            break


def _check_upstream_lock(root: Path, errors: list[str]) -> None:
    lock_path = root / "upstream" / "vendor-lock.json"
    if not lock_path.is_file():
        errors.append("missing upstream/vendor-lock.json")
        return
    try:
        payload = json.loads(_read_text(lock_path))
    except json.JSONDecodeError:
        return
    if "schema_version" not in payload:
        errors.append("upstream lock missing schema_version")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("upstream lock missing sources")
        return
    for source in sources:
        identity = str(source.get("id", "?"))
        revision = str(source.get("revision", ""))
        if not HEX64.fullmatch(revision):
            errors.append(f"upstream lock revision is not hex: {identity}")
        canonical = source.get("canonical_path")
        if not isinstance(canonical, str) or not canonical:
            errors.append(f"upstream lock missing canonical_path: {identity}")
        elif not (root / canonical).exists():
            errors.append(f"upstream lock canonical_path missing: {canonical}")


def _check_generated_drift(root: Path, errors: list[str]) -> None:
    lock_path = root / "harness.lock"
    if not lock_path.is_file():
        errors.append("missing harness.lock")
        return
    try:
        recorded = json.loads(_read_text(lock_path))
    except json.JSONDecodeError:
        return
    current = build_lock(root)
    if recorded.get("generated_hashes") != current["generated_hashes"]:
        errors.append("generated hash drift vs harness.lock")


def validate_repository(root: Path) -> ValidationResult:
    root = Path(root)
    errors: list[str] = []
    _check_parseable(root, errors)
    _check_skills(root, errors)
    _check_appledouble_bak(root, errors)
    _check_absolute_paths(root, errors)
    _check_production_targets(root, errors)
    _check_constitution_models(root, errors)
    _check_upstream_lock(root, errors)
    _check_generated_drift(root, errors)
    return ValidationResult(errors=tuple(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the canonical harness tree")
    parser.add_argument("root", type=Path, nargs="?", default=Path("."))
    args = parser.parse_args(argv)
    result = validate_repository(args.root)
    for error in result.errors:
        print(error, file=sys.stderr)
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
