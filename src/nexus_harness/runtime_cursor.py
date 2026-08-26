from __future__ import annotations

import ipaddress
import json
import re
import tomllib
from pathlib import Path

from nexus_harness.adapters import RenderedFile
from nexus_harness.runtime_common import (
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

_HOSTNAME = re.compile(r"^[A-Za-z0-9.-]+$")


def _is_valid_hostname(value: str) -> bool:
    if len(value) > 253 or not _HOSTNAME.fullmatch(value):
        return False
    labels = value.split(".")
    return all(
        0 < len(label) <= 63 and label[0].isalnum() and label[-1].isalnum()
        for label in labels
    )


def _allowed_hosts(root: Path) -> list[str]:
    path = root / "profiles" / "active.toml"
    if not path.is_file():
        return []
    try:
        profile = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return []
    network = profile.get("network")
    if not isinstance(network, dict):
        return []
    values = network.get("allowed_hosts")
    if not isinstance(values, list):
        return []
    hosts = set()
    for value in values:
        if not isinstance(value, str) or not _is_valid_hostname(value):
            continue
        try:
            ipaddress.ip_address(value)
        except ValueError:
            hosts.add(value)
    return sorted(hosts)


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
            generated_markdown(_RULES).encode("utf-8"),
        ),
        RenderedFile(
            "cursor/sandbox.json",
            generated_json(sandbox).encode("utf-8"),
        ),
    )
