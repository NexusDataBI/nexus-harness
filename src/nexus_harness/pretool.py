"""PreToolUse policy against canonical filesystem/network/production/approvals."""

from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

from nexus_harness.config import load_toml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_POLICY_ROOT = _REPO_ROOT / "core" / "policies"


def _load(name: str) -> dict:
    return load_toml(_POLICY_ROOT / name)


def _tool_name(payload: dict) -> str | None:
    for key in ("tool_name", "toolName", "tool"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _tool_input(payload: dict) -> dict | None:
    for key in ("tool_input", "toolInput", "input"):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            return value
        return None
    return {}


def _approvals(payload: dict) -> set[str]:
    raw = payload.get("approvals_recorded") or payload.get("approvals") or []
    if isinstance(raw, bool):
        return {"explicit"} if raw else set()
    if isinstance(raw, dict):
        raw = raw.keys()
    try:
        return {str(item) for item in raw}
    except TypeError:
        return set()


def _matches_denied(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    posix = PurePosixPath(normalized)
    for pattern in patterns:
        if posix.match(pattern) or fnmatch.fnmatch(normalized, pattern):
            return True
        if pattern.endswith("/**") and (
            normalized == pattern[:-3] or normalized.startswith(pattern[:-3] + "/")
        ):
            return True
    return False


def evaluate_pretool(payload: dict) -> tuple[int, dict]:
    if payload.get("deny") is True:
        return 2, {"denied": True, "reason": "explicit deny"}
    tool = _tool_name(payload)
    tool_input = _tool_input(payload)
    if tool is None or tool_input is None:
        return 2, {"denied": True, "reason": "invalid PreToolUse payload"}

    filesystem = _load("filesystem.toml")
    network = _load("network.toml")
    production = _load("production.toml")
    approvals = _load("approvals.toml")
    granted = _approvals(payload)

    path = str(
        tool_input.get("path")
        or tool_input.get("file_path")
        or tool_input.get("filePath")
        or ""
    )
    command = str(tool_input.get("command") or tool_input.get("cmd") or "")
    url = str(tool_input.get("url") or tool_input.get("href") or "")
    blob = " ".join([tool, path, command, url]).lower()

    deny_globs = list(filesystem.get("deny_patterns", {}).get("relative_globs") or [])
    if path and _matches_denied(path, deny_globs):
        return 2, {"denied": True, "reason": "filesystem deny pattern"}

    production_markers = (
        "production",
        "prod-deploy",
        "docker compose",
        "kubectl",
        "helm upgrade",
        "ssh ",
        "scp ",
    )
    needs_production = any(marker in blob for marker in production_markers)
    if needs_production and filesystem.get("production", {}).get(
        "implicit_production_write_forbidden", True
    ):
        if "production" not in granted and "explicit" not in granted:
            if production.get("deploy", {}).get(
                "requires_explicit_gate", True
            ) or network.get("production", {}).get("never_implicit", True):
                return 2, {"denied": True, "reason": "production requires approval"}

    destructive = ("rm -rf", "drop table", "mkfs", "format ", ":(){:|:&};:")
    if any(item in blob for item in destructive):
        if approvals.get("required", {}).get("destructive_action", True):
            if "destructive" not in granted and "explicit" not in granted:
                return 2, {
                    "denied": True,
                    "reason": "destructive action requires approval",
                }

    return 0, {"allowed": True, "tool_name": tool}
