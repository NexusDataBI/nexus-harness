"""Normalize runtime problems into provider-independent incident candidates.

Consumes already-decoded PostHog problem objects (not raw HTTP). Fingerprints
are deterministic over stable identity fields only — volatile IDs, timestamps,
and unnecessary PII never participate. Root/escape cause stay UNKNOWN until
diagnosis; proximate symptom may be KNOWN from the observed error.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Any, Mapping

from nexus_harness.posthog import safe_session_link, sanitize_public_text

UNKNOWN = "UNKNOWN"
KNOWN = "KNOWN"
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_HEX_ADDR = re.compile(r"\b0x[0-9a-fA-F]+\b")


@dataclass(frozen=True)
class IncidentCandidate:
    """Provider-independent incident candidate produced from a runtime problem."""

    project: str
    environment: str
    error_type: str
    stack_location: str
    route: str | None
    release: str | None
    occurrences: int
    affected_users: int
    first_seen: str | None
    last_seen: str | None
    fingerprint: str
    proximate_symptom: str
    root_cause: str
    escape_cause: str
    symptom: str | None = None
    provider_problem_id: str | None = None
    session_ids: tuple[str, ...] = ()
    session_links: tuple[str, ...] = ()


def normalize_posthog_problem(problem: Mapping[str, Any]) -> IncidentCandidate:
    """Map a decoded PostHog problem dict into an IncidentCandidate.

    Does not call the network. Does not invent root-cause analysis.
    """
    data = dict(problem)
    project = _text(data.get("project"))
    environment = _text(data.get("environment"))
    error_type = _text(data.get("error_type") or data.get("exception_type"))
    stack_location = _normalize_stack_location(
        data.get("stack_location") or data.get("location") or ""
    )
    if not project or not environment or not error_type or not stack_location:
        raise ValueError("incident identity is incomplete")
    route = _normalize_route(data.get("route") or data.get("feature"))
    release = _optional_text(data.get("release"))
    occurrences = _int(data.get("occurrences"), default=1)
    affected_users = _int(data.get("affected_users") or data.get("users"), default=0)
    first_seen = _optional_text(data.get("first_seen"))
    last_seen = _optional_text(data.get("last_seen"))
    problem_id = _optional_text(data.get("problem_id") or data.get("id"))
    session_ids = _session_ids(data)
    session_links = tuple(
        link for link in (_safe_link(item) for item in _session_links(data)) if link
    )
    exception_message = _optional_text(
        sanitize_public_text(data.get("exception_message") or data.get("message") or "")
    )

    fingerprint = _fingerprint(
        project=project,
        environment=environment,
        error_type=error_type,
        stack_location=stack_location,
        route=route,
    )

    proximate = KNOWN if error_type or exception_message or stack_location else UNKNOWN
    symptom = exception_message or error_type or None

    return IncidentCandidate(
        project=project,
        environment=environment,
        error_type=error_type,
        stack_location=stack_location,
        route=route,
        release=release,
        occurrences=occurrences,
        affected_users=affected_users,
        first_seen=first_seen,
        last_seen=last_seen,
        fingerprint=fingerprint,
        proximate_symptom=proximate,
        root_cause=UNKNOWN,
        escape_cause=UNKNOWN,
        symptom=symptom,
        provider_problem_id=problem_id,
        session_ids=session_ids,
        session_links=session_links,
    )


def _fingerprint(
    *,
    project: str,
    environment: str,
    error_type: str,
    stack_location: str,
    route: str | None,
) -> str:
    """Hash only stable identity fields — never PII or volatile IDs."""
    parts = (
        project,
        environment,
        error_type,
        stack_location,
        route or "",
    )
    payload = "\0".join(parts).encode("utf-8")
    return sha256(payload).hexdigest()


def _normalize_route(raw: Any) -> str | None:
    text = _optional_text(raw)
    if text is None:
        return None
    text = text.split("?", 1)[0]
    return sanitize_public_text(text) or None


def _safe_link(value: str) -> str | None:
    return safe_session_link(value)


def _normalize_stack_location(raw: Any) -> str:
    text = " ".join(str(raw or "").split())
    text = _UUID.sub(" ", text)
    text = _HEX_ADDR.sub(" ", text)
    return " ".join(text.split())


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _int(value: Any, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _session_ids(data: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    single = _optional_text(data.get("session_id"))
    if single:
        values.append(single)
    raw = data.get("session_ids")
    if isinstance(raw, (list, tuple)):
        for item in raw:
            text = _optional_text(item)
            if text and text not in values:
                values.append(text)
    return tuple(values)


def _session_links(data: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    single = _optional_text(data.get("session_url") or data.get("session_link"))
    if single:
        values.append(single)
    raw = data.get("session_links") or data.get("session_urls")
    if isinstance(raw, (list, tuple)):
        for item in raw:
            text = _optional_text(item)
            if text and text not in values:
                values.append(text)
    return tuple(values)
