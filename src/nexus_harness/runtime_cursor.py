from __future__ import annotations

import json
import tomllib
from pathlib import Path

from nexus_harness.adapters import RenderedFile
from nexus_harness.runtime_common import (
    GENERATED_MARKER,
    generated_json,
    generated_markdown,
)


_SANDBOX_SOURCE = (
    Path(__file__).resolve().parents[2] / "adapters" / "cursor" / "sandbox.base.json"
)

_RULES = """# Cursor workflow

Nexus Harness is the source of truth for lifecycle state and completion.

- Follow the canonical workflow stages and approval boundaries.
- Treat the deterministic completion gate as authoritative; do not claim completion
  when it fails.
- Use the runtime-neutral Nexus hook and command path at lifecycle boundaries.
- Nexus Memory is the canonical cross-session engineering memory layer.
- Use public `nexus_harness.memory` APIs (`session_recall`,
  `checkpoint_memory_candidates`, `restore_memory_candidates`,
  `collect_memory_candidates`, and `consolidate_memory`) for bounded recall.
- Restore structured task state before rebuilding context after compaction.
- Checkpoint structured state before compaction; never persist a transcript as
  canonical memory.
- Candidate, stale, invalid, or confidential memory is not automatically injected.
- A failed completion gate must not consolidate memory.
- Never expose secrets or invent context when memory retrieval is unavailable.
"""

_PROFILE_CANDIDATES = (
    Path(".nexus/project-profile.toml"),
    Path("project-profile.toml"),
    Path("profiles/active.toml"),
    Path("profiles/project.toml"),
)


def _allowed_hosts(root: Path) -> list[str]:
    for relative in _PROFILE_CANDIDATES:
        path = root / relative
        if not path.is_file():
            continue
        try:
            profile = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        network = profile.get("network", {})
        values = network.get("allowed_hosts", network.get("allowedHosts", []))
        if not isinstance(values, list):
            return []
        return sorted({host for host in values if isinstance(host, str) and host})
    return []


def render(root: Path) -> tuple[RenderedFile, ...]:
    root = Path(root)
    with _SANDBOX_SOURCE.open(encoding="utf-8") as source:
        sandbox = json.load(source)
    sandbox["networkPolicy"]["default"] = "deny"
    sandbox["networkPolicy"]["allowedHosts"] = _allowed_hosts(root)
    return (
        RenderedFile("USER_RULES.md", generated_markdown(_RULES).encode("utf-8")),
        RenderedFile(
            ".cursor/rules/nexus-workflow.mdc",
            generated_markdown(f"<!-- {GENERATED_MARKER} -->\n{_RULES}").encode(
                "utf-8"
            ),
        ),
        RenderedFile(
            "cursor/sandbox.json",
            generated_json(sandbox).encode("utf-8"),
        ),
    )
