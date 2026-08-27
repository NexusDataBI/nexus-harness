"""Render and optionally submit runtime incidents as GitHub Issues.

Reuses Plan 5 ``github.GitHub`` and the Issue Contract. Maps IncidentCandidate
to work type ``bug`` with source ``runtime_incident/posthog``. Remote mutation
is unauthorized by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus_harness.incident_policy import (
    ACTION_CREATE,
    ACTION_UPDATE,
    incident_marker,
)
from nexus_harness.incidents import IncidentCandidate, UNKNOWN
from nexus_harness.posthog import safe_session_link, sanitize_public_text
from nexus_harness.tracking import issue_body

ISSUE_WORK_TYPE = "bug"
ISSUE_SOURCE = "runtime_incident/posthog"


@dataclass(frozen=True)
class IncidentIssueResult:
    action: str
    request_title: str
    request_body: str
    issue_number: int | None = None
    mutated: bool = False


def render_incident_issue(
    candidate: IncidentCandidate,
    *,
    digest: str | None = None,
    **ignored: Any,
) -> str:
    """Issue Contract body. Secrets in kwargs are ignored, never interpolated."""
    _ = ignored  # callers may pass tokens; they must not appear in the body
    marker = incident_marker(candidate.fingerprint)
    digest_text = digest if digest else UNKNOWN
    evidence = [
        f"source: {ISSUE_SOURCE}",
        f"project: {candidate.project}",
        f"environment: {candidate.environment}",
        f"release: {candidate.release or UNKNOWN}",
        f"deployment_digest: {digest_text}",
        f"occurrences: {candidate.occurrences}",
        f"affected_users: {candidate.affected_users}",
        f"posthog_problem_id: {candidate.provider_problem_id or UNKNOWN}",
    ]
    if candidate.session_ids:
        evidence.append(
            "session_ids: "
            + ", ".join(sanitize_public_text(item) for item in candidate.session_ids)
        )
    if candidate.session_links:
        links = [safe_session_link(item) for item in candidate.session_links]
        links = [item for item in links if item]
        if links:
            evidence.append("session_links: " + ", ".join(links))
    evidence.append(marker)

    symptom = sanitize_public_text(candidate.symptom or candidate.error_type or "")
    fields = {
        "Summary": sanitize_public_text(
            f"{candidate.error_type} at {candidate.stack_location}"
            if candidate.error_type or candidate.stack_location
            else "Runtime incident"
        ),
        "Type": ISSUE_WORK_TYPE,
        "Priority": _priority(candidate),
        "Project/Area": candidate.project,
        "Problem or desired outcome": symptom or "Runtime error observed in PostHog",
        "Acceptance Criteria": (
            "Error no longer reproduces on the current release; "
            "root and escape causes recorded after diagnosis."
        ),
        "Risk/Environment": sanitize_public_text(
            f"{candidate.environment} / route {candidate.route or UNKNOWN}"
        ),
        "Evidence links when bug/incident": "\n".join(evidence),
        "Dependencies": "",
        "Reproduction": symptom or UNKNOWN,
        "Proximate Cause": candidate.proximate_symptom or UNKNOWN,
        "Root Cause": UNKNOWN,
        "Escape Cause": UNKNOWN,
        "Regression Guard": "",
        "Preventive Control": "",
    }
    return issue_body(ISSUE_WORK_TYPE, fields)


def apply_incident_issue(
    candidate: IncidentCandidate,
    github: object,
    *,
    repo: str,
    action: str,
    digest: str | None = None,
    issue_number: int | None = None,
    authorize_remote_mutation: bool = False,
) -> IncidentIssueResult:
    body = render_incident_issue(candidate, digest=digest)
    title = _title(candidate)
    if action == ACTION_UPDATE:
        number = int(issue_number or 0) or None
        mutated = False
        if authorize_remote_mutation and number is not None:
            github.edit_issue(repo, number, body=body)
            mutated = True
        return IncidentIssueResult(
            action=ACTION_UPDATE,
            request_title=title,
            request_body=body,
            issue_number=number,
            mutated=mutated,
        )

    mutated = False
    number = None
    if action == ACTION_CREATE and authorize_remote_mutation:
        created = github.create_issue(repo, title, body)
        number = int(getattr(created, "number", 0) or 0) or None
        mutated = True
    return IncidentIssueResult(
        action=ACTION_CREATE if action == ACTION_CREATE else action,
        request_title=title,
        request_body=body,
        issue_number=number,
        mutated=mutated,
    )


def _title(candidate: IncidentCandidate) -> str:
    loc = candidate.stack_location or candidate.error_type or "runtime incident"
    return f"{candidate.error_type or 'Error'}: {loc}".strip()


def _priority(candidate: IncidentCandidate) -> str:
    if candidate.occurrences >= 3 or candidate.affected_users >= 2:
        return "high"
    return "medium"
