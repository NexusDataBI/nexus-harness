from __future__ import annotations

from pathlib import Path

from nexus_harness.adapters import RenderedFile
from nexus_harness.runtime_common import (
    constitution_with_notes,
    generated_markdown,
    generated_toml_header,
)


_CONFIG_SOURCE = (
    Path(__file__).resolve().parents[2] / "adapters" / "codex" / "config.base.toml"
)

_CODEX_NOTES = """# Codex-specific notes

Nexus Harness is the source of truth. Nexus Memory is injected only by the runtime-neutral command, with JSON on stdin:

`python3 hooks/nexus_event.py --event <EventName>`

Do not invent a parallel memory or completion path. Candidate, stale, invalid, or confidential memory is not automatically injected. A failed completion gate must not consolidate memory.
"""


def render(root: Path) -> tuple[RenderedFile, ...]:
    root = Path(root)
    config = _CONFIG_SOURCE.read_text(encoding="utf-8")
    return (
        RenderedFile(
            "AGENTS.md",
            generated_markdown(constitution_with_notes(root, _CODEX_NOTES)).encode(
                "utf-8"
            ),
        ),
        RenderedFile(
            "codex/config.toml",
            f"{generated_toml_header()}{config}".encode("utf-8"),
        ),
    )
