from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenderedFile:
    relative_path: str
    content: bytes


def render_all(root: Path) -> tuple[RenderedFile, ...]:
    from nexus_harness.runtime_claude import render as render_claude
    from nexus_harness.runtime_codex import render as render_codex
    from nexus_harness.runtime_cursor import render as render_cursor

    files = [*render_claude(root), *render_cursor(root), *render_codex(root)]
    return tuple(sorted(files, key=lambda item: item.relative_path))
