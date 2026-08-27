"""Actionability and open-Issue deduplication for runtime incidents.

Thresholds live in ``core/observability/incidents.toml``. Invalid policy
fails closed: never automatically CREATE_ISSUE. Dedup uses an exact body
marker, never fuzzy title matching.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus_harness.config import load_toml

ACTION_IGNORE = "IGNORE"
ACTION_UPDATE = "UPDATE_EXISTING"
ACTION_CREATE = "CREATE_ISSUE"
ACTION_POLICY_FAILURE = "POLICY_FAILURE"

MARKER_PREFIX = "<!-- nexus-incident:"
MARKER_SUFFIX = " -->"

_CORE = Path(__file__).resolve().parents[2] / "core" / "observability"
DEFAULT_POLICY_PATH = _CORE / "incidents.toml"


@dataclass(frozen=True)
class IncidentPolicy:
    min_occurrences_create: int
    min_affected_users_create: int
    release_regression: bool
    fatal: bool
    security_adjacent: bool


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    issue_number: int | None = None
    reason: str = ""


def incident_marker(fingerprint: str) -> str:
    """Stable exact marker stored in GitHub Issue bodies."""
    fp = str(fingerprint or "").strip()
    return f"{MARKER_PREFIX}{fp}{MARKER_SUFFIX}"


def load_incident_policy(path: Path | None = None) -> IncidentPolicy:
    source = Path(path) if path is not None else DEFAULT_POLICY_PATH
    if not source.is_file():
        raise ValueError("incident policy file is missing")
    raw = load_toml(source)
    thresholds = raw.get("thresholds")
    priority = raw.get("priority")
    if not isinstance(thresholds, dict) or not isinstance(priority, dict):
        raise ValueError("incident policy thresholds/priority must be tables")
    min_occ = _positive_int(thresholds.get("min_occurrences_create"))
    min_users = _positive_int(thresholds.get("min_affected_users_create"))
    return IncidentPolicy(
        min_occurrences_create=min_occ,
        min_affected_users_create=min_users,
        release_regression=_require_bool(priority.get("release_regression")),
        fatal=_require_bool(priority.get("fatal")),
        security_adjacent=_require_bool(priority.get("security_adjacent")),
    )


def classify_incident(
    occurrences: int | None = None,
    affected_users: int | None = None,
    regression: bool = False,
    fatal: bool = False,
    *,
    fingerprint: str | None = None,
    open_issues: Sequence[Any] = (),
    security_adjacent: bool = False,
    policy: IncidentPolicy | None = None,
    policy_path: Path | None = None,
) -> PolicyDecision:
    try:
        rules = policy or load_incident_policy(policy_path)
    except (TypeError, ValueError, OSError) as exc:
        return PolicyDecision(
            action=ACTION_POLICY_FAILURE,
            reason=str(exc) or "invalid incident policy",
        )

    match = _matching_open_issue(fingerprint, open_issues)
    if match is not None:
        return PolicyDecision(
            action=ACTION_UPDATE,
            issue_number=match,
            reason="open issue with exact fingerprint marker",
        )

    occ = _as_int(occurrences, default=0)
    users = _as_int(affected_users, default=0)
    if rules.fatal and fatal:
        return PolicyDecision(action=ACTION_CREATE, reason="fatal")
    if rules.security_adjacent and security_adjacent:
        return PolicyDecision(action=ACTION_CREATE, reason="security-adjacent")
    crossed = (
        occ >= rules.min_occurrences_create or users >= rules.min_affected_users_create
    )
    if not crossed:
        return PolicyDecision(action=ACTION_IGNORE, reason="below actionable threshold")
    if rules.release_regression and regression:
        return PolicyDecision(action=ACTION_CREATE, reason="release regression")
    if occ >= rules.min_occurrences_create:
        return PolicyDecision(action=ACTION_CREATE, reason="occurrence threshold")
    return PolicyDecision(action=ACTION_CREATE, reason="affected-user threshold")


def _matching_open_issue(
    fingerprint: str | None, open_issues: Sequence[Any]
) -> int | None:
    fp = str(fingerprint or "").strip()
    if not fp:
        return None
    marker = incident_marker(fp)
    for item in open_issues or ():
        if not _is_open(item):
            continue
        body = _field(item, "body")
        if marker not in body:
            continue
        number = _positive_issue(_field(item, "number"))
        if number is not None:
            return number
    return None


def _is_open(item: Any) -> bool:
    state = _field(item, "state").strip().lower()
    return state in {"", "open"}


def _field(item: Any, name: str) -> str:
    if isinstance(item, Mapping):
        value = item.get(name, "")
    else:
        value = getattr(item, name, "")
    return str(value or "")


def _positive_issue(value: str) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _as_int(value: Any, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _positive_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError("threshold must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("threshold must be a positive integer") from exc
    if number < 1:
        raise ValueError("threshold must be a positive integer")
    return number


def _require_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("priority flags must be explicit booleans")
