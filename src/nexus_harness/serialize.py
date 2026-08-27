"""Canonical safe serialization for logs, CLI, doctor, and reports.

Secret-bearing objects (notably ``PostHogConfig``) must never enter
``dataclasses.asdict`` / generic JSON paths. Callers serialize via
``safe_serialize`` / ``dumps_report``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from typing import Any

_REDACTED = "[REDACTED]"
_SECRET_KEYS = frozenset(
    {
        "personal_api_key",
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "authorization",
        "cookie",
        "cookies",
    }
)


def safe_serialize(value: Any) -> Any:
    """Recursively convert ``value`` into JSON-safe data with secrets redacted."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value
    safe_dict = getattr(value, "safe_dict", None)
    if callable(safe_dict):
        return safe_serialize(safe_dict())
    if is_dataclass(value) and not isinstance(value, type):
        out: dict[str, Any] = {}
        for item in fields(value):
            raw = getattr(value, item.name)
            if item.name.casefold() in _SECRET_KEYS or item.metadata.get("secret"):
                out[item.name] = _REDACTED if raw else None
            else:
                out[item.name] = safe_serialize(raw)
        return out
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            name = str(key)
            if name.casefold() in _SECRET_KEYS:
                out[name] = _REDACTED if item else None
            else:
                out[name] = safe_serialize(item)
        return out
    if isinstance(value, (set, frozenset)):
        return sorted(safe_serialize(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [safe_serialize(item) for item in value]
    return str(value)


def dumps_report(value: Any) -> str:
    """Deterministic JSON for CLI/doctor/report stdout. Never includes secrets."""
    return json.dumps(safe_serialize(value), sort_keys=True, default=str)


def observability_cli_json(config: Any) -> str:
    """Machine JSON for any CLI that must display PostHog/observability config."""
    return dumps_report({"status": "ok", "posthog": config})


def observability_doctor_report(config: Any) -> dict[str, Any]:
    """Doctor-facing PostHog summary. Safe to print or embed in JSON."""
    payload = safe_serialize(config)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    enabled = bool(payload.get("enabled"))
    status = "PASS" if enabled else "ACTIVATION_REQUIRED"
    return {
        "check": "posthog",
        "status": status,
        "config": payload,
    }
