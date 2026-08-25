from __future__ import annotations

import json
import os
import re
from pathlib import Path

from nexus_harness.config import load_toml
from nexus_harness.memory.guard import validate_memory_record
from nexus_harness.memory.models import MemoryRecord, MemoryType

_REPO_ROOT = Path(__file__).resolve().parents[3]
_POLICY_PATH = _REPO_ROOT / "core" / "memory" / "memory-policy.toml"
_TEMPLATE_README = _REPO_ROOT / "templates" / "memory" / "project-memory" / "README.md"

CATEGORY_BY_TYPE = {
    MemoryType.DECISION: "decisions",
    MemoryType.INVARIANT: "invariants",
    MemoryType.COMPONENT: "components",
    MemoryType.PATTERN: "patterns",
    MemoryType.LESSON: "lessons",
    MemoryType.INCIDENT: "incidents",
}

_MEMORY_ID_RE = re.compile(r"^mem-[a-z]+-[a-z0-9-]+-[0-9a-f]{8}$")


class MemoryStoreError(ValueError):
    """Raised when project memory files are missing, duplicated or invalid."""


def _assert_safe_memory_id(memory_id: str) -> None:
    if (
        not memory_id
        or ".." in memory_id
        or "/" in memory_id
        or "\\" in memory_id
        or not _MEMORY_ID_RE.fullmatch(memory_id)
    ):
        raise MemoryStoreError("unsafe memory id")


def _assert_inside_dir(path: Path, directory: Path) -> None:
    if not path.resolve().is_relative_to(directory.resolve()):
        raise MemoryStoreError("unsafe memory id")


def _project_memory_root(project_root: Path) -> Path:
    policy = load_toml(_POLICY_PATH)
    relative = policy.get("storage", {}).get("project_relative_path", ".nexus/memory")
    return Path(project_root) / relative


def _category_dir(project_root: Path, memory_type: MemoryType) -> Path:
    return _project_memory_root(project_root) / CATEGORY_BY_TYPE[memory_type]


def _sidecar_paths(project_root: Path) -> list[Path]:
    memory_root = _project_memory_root(project_root)
    paths: list[Path] = []
    for category in CATEGORY_BY_TYPE.values():
        directory = memory_root / category
        if not directory.is_dir():
            continue
        paths.extend(
            sorted(
                path
                for path in directory.iterdir()
                if path.is_file()
                and path.suffix == ".json"
                and not path.name.endswith(".tmp")
            )
        )
    return paths


def _load_sidecar(path: Path) -> MemoryRecord:
    data = json.loads(path.read_text(encoding="utf-8"))
    return MemoryRecord.from_json_dict(data)


def _render_markdown(record: MemoryRecord) -> str:
    lines = [
        f"# {record.title}",
        "",
        record.body,
        "",
        "## Nexus Memory",
        "",
        f"- ID: `{record.id}`",
        f"- Status: {record.status.value}",
        f"- Type: {record.type.value}",
    ]
    if record.sources:
        lines.append("- Sources:")
        for source in record.sources:
            lines.append(f"  - {source.kind}: {source.ref}")
    else:
        lines.append("- Sources: none")
    lines.append("")
    return "\n".join(lines)


def _write_temp_file(path: Path, data: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _cleanup_temps(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def init_project_memory(project_root: Path) -> Path:
    memory_root = _project_memory_root(project_root)
    memory_root.mkdir(parents=True, exist_ok=True)
    for category in CATEGORY_BY_TYPE.values():
        (memory_root / category).mkdir(parents=True, exist_ok=True)
    readme = memory_root / "README.md"
    if not readme.exists():
        readme.write_text(
            _TEMPLATE_README.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return memory_root


def write_memory(
    project_root: Path, record: MemoryRecord, *, replace: bool = False
) -> MemoryRecord:
    _assert_safe_memory_id(record.id)
    validate_memory_record(record)
    existing_paths = [
        path for path in _sidecar_paths(project_root) if path.stem == record.id
    ]
    if existing_paths:
        if len(existing_paths) != 1:
            raise MemoryStoreError(
                f"expected exactly one sidecar for {record.id}; found {len(existing_paths)}"
            )
        existing = _load_sidecar(existing_paths[0])
        if not replace:
            if existing != record:
                raise MemoryStoreError(f"duplicate memory id: {record.id}")
            return existing
        if (
            existing.id != record.id
            or existing.type != record.type
            or existing.scope != record.scope
            or existing.project_id != record.project_id
        ):
            raise MemoryStoreError(
                f"replace requires stable id/type/scope/project_id for {record.id}"
            )

    category_dir = _category_dir(project_root, record.type)
    category_dir.mkdir(parents=True, exist_ok=True)
    md_path = category_dir / f"{record.id}.md"
    json_path = category_dir / f"{record.id}.json"
    md_tmp = category_dir / f"{record.id}.md.tmp"
    json_tmp = category_dir / f"{record.id}.json.tmp"
    for path in (md_path, json_path, md_tmp, json_tmp):
        _assert_inside_dir(path, category_dir)
    try:
        _write_temp_file(md_tmp, _render_markdown(record))
        _write_temp_file(json_tmp, json.dumps(record.to_json_dict(), indent=2) + "\n")
        os.replace(json_tmp, json_path)
        os.replace(md_tmp, md_path)
    except Exception:
        _cleanup_temps(md_tmp, json_tmp)
        raise
    return record


def read_memory(project_root: Path, memory_id: str) -> MemoryRecord:
    matches = [p for p in _sidecar_paths(project_root) if p.stem == memory_id]
    if len(matches) != 1:
        raise MemoryStoreError(
            f"expected exactly one sidecar for {memory_id}; found {len(matches)}"
        )
    data = json.loads(matches[0].read_text(encoding="utf-8"))
    return MemoryRecord.from_json_dict(data)


def load_project_memories(project_root: Path) -> list[MemoryRecord]:
    records = [
        MemoryRecord.from_json_dict(json.loads(p.read_text(encoding="utf-8")))
        for p in _sidecar_paths(project_root)
    ]
    ids = [r.id for r in records]
    if len(ids) != len(set(ids)):
        raise MemoryStoreError("duplicate memory id")
    return sorted(records, key=lambda r: r.id)
