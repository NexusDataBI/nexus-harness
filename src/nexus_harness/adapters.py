from dataclasses import dataclass
from pathlib import Path

from nexus_harness.runtime_common import NEXUS_EVENT_WRAPPER


@dataclass(frozen=True)
class RenderedFile:
    """A generated runtime file owned by the harness compiler."""

    relative_path: str
    content: bytes


def render_all(root: Path) -> tuple[RenderedFile, ...]:
    from nexus_harness.runtime_claude import render as render_claude
    from nexus_harness.runtime_codex import render as render_codex
    from nexus_harness.runtime_cursor import render as render_cursor

    files = [
        RenderedFile("hooks/nexus_event.py", NEXUS_EVENT_WRAPPER.encode("utf-8")),
        *render_claude(root),
        *render_cursor(root),
        *render_codex(root),
    ]
    return tuple(sorted(files, key=lambda item: item.relative_path))
