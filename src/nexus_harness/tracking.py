"""Issue tracking gate: require, find-or-create, and contract bodies.

Remote mutation is unauthorized by default. Search before create.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from nexus_harness.github import Issue
from nexus_harness.state import TaskState

_MUTABLE_WORK_TYPES = frozenset(
    {
        "change",
        "bugfix",
        "bug",
        "improvement",
        "feature",
        "migration",
        "migrate",
        "debug",
    }
)
_READ_ONLY_WORK_TYPES = frozenset(
    {
        "inspect",
        "research",
        "explanation",
        "read-only",
        "readonly",
    }
)
_BUG_WORK_TYPES = frozenset({"bug", "bugfix", "debug"})

CONTRACT_SECTIONS = (
    "Summary",
    "Type",
    "Priority",
    "Project/Area",
    "Problem or desired outcome",
    "Acceptance Criteria",
    "Risk/Environment",
    "Evidence links when bug/incident",
    "Dependencies",
)
BUG_RCA_SECTIONS = (
    "Reproduction",
    "Proximate Cause",
    "Root Cause",
    "Escape Cause",
    "Regression Guard",
    "Preventive Control",
)


@dataclass
class TrackingResult:
    issue: int | None
    url: str = ""
    created: bool = False


def tracking_required(work_type: str, mutable: bool | None = None) -> bool:
    kind = (work_type or "").strip().lower()
    if mutable is False:
        return False
    if kind in _READ_ONLY_WORK_TYPES:
        return bool(mutable)
    if kind in _MUTABLE_WORK_TYPES:
        return True if mutable is None else bool(mutable)
    return bool(mutable)


def issue_body(
    work_type: str,
    fields: Mapping[str, str] | None = None,
) -> str:
    values = {str(key): str(value) for key, value in (fields or {}).items()}
    values.setdefault("Type", work_type)
    sections = list(CONTRACT_SECTIONS)
    if work_type.strip().lower() in _BUG_WORK_TYPES:
        sections.extend(BUG_RCA_SECTIONS)
    blocks: list[str] = []
    for heading in sections:
        blocks.append(f"## {heading}")
        blocks.append("")
        blocks.append(values.get(heading, "").strip())
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def ensure_issue(
    state: TaskState,
    github: object,
    *,
    title: str,
    work_type: str,
    repo: str | None = None,
    fingerprint: str | None = None,
    authorize_remote_mutation: bool = False,
    fields: Mapping[str, str] | None = None,
) -> TrackingResult:
    target_repo = repo or state.repo_id
    existing = _positive(state.issue)
    if existing is not None:
        current = _view_existing(github, target_repo, existing)
        if current is not None and _is_open(current):
            return _bind(state, current, created=False)

    found = github.find_issue(target_repo, fingerprint or title)
    if found is not None and _positive(found.number) and _is_open(found):
        return _bind(state, found, created=False)

    if not authorize_remote_mutation:
        state.issue = None
        return TrackingResult(issue=None, url="", created=False)

    created = github.create_issue(
        target_repo,
        title,
        issue_body(work_type, fields),
    )
    return _bind(state, created, created=True)


def _bind(state: TaskState, issue: Issue, *, created: bool) -> TrackingResult:
    number = _positive(issue.number)
    state.issue = number
    return TrackingResult(
        issue=number,
        url=str(getattr(issue, "url", "") or ""),
        created=created,
    )


def _view_existing(github: object, repo: str, number: int) -> Issue | None:
    view = getattr(github, "view_issue", None)
    found = (
        view(repo, number) if callable(view) else github.find_issue(repo, str(number))
    )
    if found is None:
        return None
    if _positive(getattr(found, "number", None)) != number:
        return None
    return found


def _positive(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number < 1:
        return None
    return number


def _is_open(issue: object) -> bool:
    state = str(getattr(issue, "state", "") or "").strip().lower()
    return state in {"", "open"}
