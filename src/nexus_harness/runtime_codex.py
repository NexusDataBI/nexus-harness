from __future__ import annotations

from pathlib import Path

from nexus_harness.adapters import RenderedFile
from nexus_harness.runtime_common import generated_markdown, generated_toml_header


_CONFIG_SOURCE = (
    Path(__file__).resolve().parents[2] / "adapters" / "codex" / "config.base.toml"
)

_AGENTS = """# Codex workflow

Nexus Harness is the source of truth for workflow state and completion.

- Follow the canonical workflow stages and approval boundaries.
- Treat the deterministic completion gate as authoritative; do not claim completion
  when it fails.
- Use Codex's project instructions and command execution capabilities to apply the
  runtime-neutral Nexus workflow at lifecycle boundaries.
- Nexus Memory is the canonical cross-session engineering memory layer.
- Use public `nexus_harness.memory` APIs (`session_recall`,
  `checkpoint_memory_candidates`, `restore_memory_candidates`,
  `collect_memory_candidates`, `consolidate_memory`, and `memory_doctor`) for
  bounded recall.
- Restore structured task state before rebuilding context after compaction.
- Checkpoint structured state before compaction; never persist a transcript as
  canonical memory.
- Candidate, stale, invalid, or confidential memory is not automatically injected.
- A failed completion gate must not consolidate memory.
- Never expose secrets or invent context when memory retrieval is unavailable.
"""


def render(root: Path) -> tuple[RenderedFile, ...]:
    del root
    config = _CONFIG_SOURCE.read_text(encoding="utf-8")
    return (
        RenderedFile("AGENTS.md", generated_markdown(_AGENTS).encode("utf-8")),
        RenderedFile(
            "codex/config.toml",
            f"{generated_toml_header()}{config}".encode("utf-8"),
        ),
    )
