from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nexus_harness.memory.models import MemoryRecord, MemoryScope
from nexus_harness.memory.store import MemoryStoreError, _is_complete_pair

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE_DIR = _REPO_ROOT / "templates" / "memory" / "portfolio-vault"
_TEMPLATE_FILES = ("HOME.md", "VAULT_RULES.md", "RETRIEVAL_PROTOCOL.md")
_VAULT_DIRS = (
    "projects",
    "domains",
    "patterns",
    "lessons",
    "decisions",
    "incidents",
    ".nexus-memory/cache",
)
_PORTFOLIO_CATEGORIES = ("patterns", "lessons", "decisions", "incidents")
_GENERATED_START = "<!-- NEXUS:GENERATED:START -->"
_GENERATED_END = "<!-- NEXUS:GENERATED:END -->"


@dataclass(frozen=True)
class ProjectBridge:
    project_id: str
    repository: str
    canonical_memory_path: str
    status: str | None = None
    current_focus: str | None = None
    related_memory_ids: tuple[str, ...] = ()


def init_portfolio_vault(target_dir: Path) -> Path:
    target = Path(target_dir)
    if target.is_file():
        raise ValueError(f"portfolio vault target is a file: {target}")
    target.mkdir(parents=True, exist_ok=True)
    for relative in _VAULT_DIRS:
        (target / relative).mkdir(parents=True, exist_ok=True)
    for name in _TEMPLATE_FILES:
        dest = target / name
        if dest.exists():
            continue
        dest.write_text(
            (_TEMPLATE_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    return target


def load_portfolio_memories(vault_root: Path) -> list[MemoryRecord]:
    records: list[MemoryRecord] = []
    for category in _PORTFOLIO_CATEGORIES:
        directory = Path(vault_root) / category
        if not directory.is_dir():
            continue
        paths = sorted(
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix == ".json"
            and not path.name.endswith(".tmp")
        )
        for path in paths:
            if not _is_complete_pair(path):
                continue
            record = MemoryRecord.from_json_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if record.scope != MemoryScope.PORTFOLIO:
                continue
            records.append(record)
    ids = [record.id for record in records]
    if len(ids) != len(set(ids)):
        raise MemoryStoreError("duplicate memory id")
    return sorted(records, key=lambda record: record.id)


def write_project_bridge(vault_root: Path, bridge: ProjectBridge) -> Path:
    project_id = bridge.project_id
    if not project_id or ".." in project_id or "/" in project_id or "\\" in project_id:
        raise ValueError("unsafe project id")
    projects_dir = Path(vault_root) / "projects"
    path = projects_dir / f"{project_id}.md"
    if not path.resolve().is_relative_to(projects_dir.resolve()):
        raise ValueError("unsafe project id")
    start = _GENERATED_START
    end = _GENERATED_END
    generated = "\n".join(
        (
            start,
            f"# {bridge.project_id}",
            f"Repository: {bridge.repository}",
            f"Canonical memory: {bridge.canonical_memory_path}",
            f"Status: {bridge.status or 'unknown'}",
            f"Current focus: {bridge.current_focus or 'not set'}",
            "Related memory: " + (", ".join(bridge.related_memory_ids) or "none"),
            end,
        )
    )
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if start in existing and end in existing:
        prefix, rest = existing.split(start, 1)
        _, suffix = rest.split(end, 1)
        content = prefix.rstrip() + "\n" + generated + suffix
    else:
        content = generated + ("\n\n" + existing.lstrip() if existing else "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
