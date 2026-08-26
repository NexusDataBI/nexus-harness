import json
from pathlib import Path

from nexus_harness.adapters import RenderedFile
from nexus_harness.runtime_common import (
    GENERATED_MARKER,
    generated_json,
    generated_markdown,
)


_SETTINGS_SOURCE = (
    Path(__file__).resolve().parents[2] / "adapters" / "claude" / "settings.base.json"
)

_CONSTITUTION = """# Claude workflow

Nexus Harness is the source of truth for workflow state and completion.

- Follow the canonical workflow stages and approval boundaries.
- Treat the deterministic completion gate as authoritative; do not claim completion
  when it fails.
- TaskCompleted must run the completion gate and exit 2 on failure.
- Nexus Memory is the canonical cross-session engineering memory layer.
- Use the generated hooks and public `nexus_harness.memory` APIs
  (`session_recall`, `checkpoint_memory_candidates`,
  `restore_memory_candidates`, `collect_memory_candidates`, and
  `consolidate_memory`) for bounded recall.
- Restore structured task state before rebuilding context after compaction.
- On PreCompact, checkpoint structured state with
  `checkpoint_memory_candidates`; never persist a transcript as canonical memory.
- On compact SessionStart, restore candidates with `restore_memory_candidates` and
  rebuild the capsule from canonical memory.
- After a passing completion gate, collect and consolidate candidates; a failing
  gate must not consolidate memory.
- Candidate, stale, invalid, or confidential memory is not automatically injected.
- Never expose secrets or invent context when memory retrieval is unavailable.
"""

_HOOK_WRAPPER = f"""# {GENERATED_MARKER}
\"\"\"Claude event bridge; lifecycle logic remains runtime-neutral.\"\"\"

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--completion-gate", action="store_true")
    args = parser.parse_args()
    try:
        from nexus_harness.hooks import dispatch
    except ImportError:
        # The common hook engine is installed by the hooks integration task.
        return 0
    try:
        dispatch(args.event, completion_gate=args.completion_gate)
    except Exception:
        if args.completion_gate:
            return 2
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""


def render(root: Path) -> tuple[RenderedFile, ...]:
    del root
    with _SETTINGS_SOURCE.open(encoding="utf-8") as source:
        settings = json.load(source)
    return (
        RenderedFile(
            "claude/CLAUDE.md", generated_markdown(_CONSTITUTION).encode("utf-8")
        ),
        RenderedFile(
            "claude/settings.json",
            generated_json(settings).encode("utf-8"),
        ),
        RenderedFile("hooks/claude_event.py", _HOOK_WRAPPER.encode("utf-8")),
    )
