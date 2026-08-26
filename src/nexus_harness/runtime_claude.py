import json
from pathlib import Path

from nexus_harness.adapters import RenderedFile
from nexus_harness.runtime_common import (
    GENERATED_MARKER,
    constitution_with_notes,
    generated_json,
    generated_markdown,
)


_SETTINGS_SOURCE = (
    Path(__file__).resolve().parents[2] / "adapters" / "claude" / "settings.base.json"
)

_CLAUDE_NOTES = """# Claude-specific notes

Claude consumes the canonical constitution above.

- TaskCompleted must run the completion gate and exit 2 on failure.
- Use generated `hooks/claude_event.py` for Claude transport; the runtime-neutral
  engine is `python3 hooks/nexus_event.py --event <EventName>`.
- On PreCompact, checkpoint structured state with
  `checkpoint_memory_candidates`; never persist a transcript as canonical memory.
- On compact SessionStart, restore candidates with `restore_memory_candidates`
  and rebuild the capsule from canonical memory.
- After a passing completion gate, collect and consolidate candidates; a failing
  gate must not consolidate memory.
- Nexus Memory is the canonical cross-session engineering memory layer.
- Bounded recall uses `session_recall` inside the generated hook engine.
"""

_HOOK_WRAPPER = (
    f"# {GENERATED_MARKER}\n"
    + '''"""Claude event bridge; lifecycle logic remains runtime-neutral."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

NEXUS_HOME = Path(__file__).resolve().parents[1]
os.environ["NEXUS_HOME"] = str(NEXUS_HOME)
sys.path.insert(0, str(NEXUS_HOME / "src"))


def _claude_transport(event, output):
    if event not in {"SessionStart", "UserPromptSubmit"}:
        return output
    parts = []
    capsule = output.get("capsule") if isinstance(output, dict) else None
    if capsule:
        parts.append(str(capsule).rstrip())
    formatted = []
    warnings = output.get("warnings") if isinstance(output, dict) else None
    for warning in warnings or []:
        if isinstance(warning, dict):
            code = str(warning.get("code") or "warning")
            message = str(warning.get("message") or "")
            formatted.append("- " + code + (": " + message if message else ""))
        else:
            formatted.append("- " + str(warning))
    if formatted:
        parts.append("\\n".join(formatted))
    return {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": "\\n\\n".join(parts),
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--completion-gate", action="store_true")
    args = parser.parse_args()
    raw = sys.stdin.read().strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return 2 if args.completion_gate else 1
    try:
        from nexus_harness.hooks import dispatch
    except ImportError:
        # The common hook engine is installed by the hooks integration task.
        return 2 if args.completion_gate else 0
    try:
        result = dispatch(args.event, payload, completion_gate=args.completion_gate)
    except Exception:
        return 2 if args.completion_gate else 1
    if result is None:
        return 2 if args.completion_gate else 0
    if getattr(result, "output", None) is not None:
        print(json.dumps(_claude_transport(args.event, result.output), default=str))
    exit_code = getattr(result, "exit_code", result)
    try:
        return int(exit_code)
    except (TypeError, ValueError):
        return 2 if args.completion_gate else 0


if __name__ == "__main__":
    sys.exit(main())
'''
)


def render(root: Path) -> tuple[RenderedFile, ...]:
    with _SETTINGS_SOURCE.open(encoding="utf-8") as source:
        settings = json.load(source)
    return (
        RenderedFile(
            "claude/CLAUDE.md",
            generated_markdown(constitution_with_notes(root, _CLAUDE_NOTES)).encode(
                "utf-8"
            ),
        ),
        RenderedFile(
            "claude/settings.json",
            generated_json(settings).encode("utf-8"),
        ),
        RenderedFile("hooks/claude_event.py", _HOOK_WRAPPER.encode("utf-8")),
    )
