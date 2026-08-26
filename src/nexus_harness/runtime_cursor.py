from __future__ import annotations

import ipaddress
import json
import re
import tomllib
from pathlib import Path

from nexus_harness.adapters import RenderedFile
from nexus_harness.runtime_common import (
    constitution_with_notes,
    generated_json,
    generated_markdown,
)


_SANDBOX_SOURCE = (
    Path(__file__).resolve().parents[2] / "adapters" / "cursor" / "sandbox.base.json"
)

_CURSOR_NOTES = """# Cursor-specific notes

Nexus Memory is injected only by the runtime-neutral command, with JSON on stdin:

`python3 hooks/nexus_event.py --event <EventName>`

Do not invent a parallel memory or completion path. Candidate, stale, invalid, or confidential memory is not automatically injected. A failed completion gate must not consolidate memory.
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
    body = constitution_with_notes(root, _CURSOR_NOTES)
    return (
        RenderedFile("USER_RULES.md", generated_markdown(body).encode("utf-8")),
        RenderedFile(
            ".cursor/rules/nexus-workflow.mdc",
            generated_markdown(body).encode("utf-8"),
        ),
        RenderedFile(
            "cursor/sandbox.json",
            generated_json(sandbox).encode("utf-8"),
        ),
    )
