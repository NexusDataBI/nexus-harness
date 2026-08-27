"""Minimal GitHub Issue hierarchy — no Jira-style ceremony.

Bounded bugs/improvements stay one Issue. Epic → Feature → Task is only the
shape for architectural/long-horizon features. Empty child Issues are never
created to fill that shape.

GitHub is the sole recoverable hierarchy authority. TaskState intentionally
does not own ``parent_issue`` / ``child_issues``. Restart recovery reads
GitHub-shaped input via ``recover_hierarchy``; local task-state roundtrip
persists only the tracking ``issue`` number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from nexus_harness.state import TaskState

_BUG_TYPES = frozenset({"bug", "bugfix"})
_FEATURE_TYPES = frozenset({"feature", "story"})
_ARCHITECTURAL_SCOPES = frozenset({"architectural", "long-horizon", "longhorizon"})

_ADD_SUB_ISSUE = """
mutation($parent: ID!, $child: ID!) {
  addSubIssue(input: { issueId: $parent, subIssueId: $child }) {
    issue { id }
    subIssue { id }
  }
}
""".strip()


@dataclass(frozen=True)
class HierarchyResult:
    shape: tuple[str, ...]
    parent: int | None = None
    children: tuple[int, ...] = ()
    linked: bool = False


def tracking_shape(
    scope: str,
    work_type: str,
    *,
    independent_deliverables: Sequence[str] | None = None,
) -> tuple[str, ...]:
    horizon = _normalize(scope).replace("_", "-")
    kind = _normalize(work_type)
    useful = _useful_deliverables(independent_deliverables)

    if kind in _BUG_TYPES:
        return ("bug",)
    if kind == "improvement":
        return ("improvement",)
    if kind in _FEATURE_TYPES:
        if horizon in _ARCHITECTURAL_SCOPES:
            return ("epic", "feature", "task")
        if useful:
            return ("feature", "task")
        return ("feature",)
    return (kind,) if kind else ("feature",)


def apply_hierarchy(
    github: object,
    *,
    repo: str,
    scope: str,
    work_type: str,
    parent: int | None = None,
    children: Sequence[int] | None = None,
    parent_id: str | None = None,
    child_ids: Sequence[str] | None = None,
    independent_deliverables: Sequence[str] | None = None,
    authorize_remote_mutation: bool = False,
    state: TaskState | None = None,
) -> HierarchyResult:
    shape = tracking_shape(
        scope,
        work_type,
        independent_deliverables=independent_deliverables,
    )
    parent_number = _positive(parent)
    planned_children = (
        tuple(number for number in (children or ()) if _positive(number) is not None)
        if _allows_children(shape)
        else ()
    )
    parent_node = _graphql_id(parent_id if parent_id is not None else parent)
    child_nodes = tuple(
        node
        for node in (
            _graphql_id(item) for item in (child_ids if child_ids is not None else ())
        )
        if node
    )
    linked = False
    if authorize_remote_mutation and parent_node and child_nodes:
        for child in child_nodes:
            github.api_graphql(
                _ADD_SUB_ISSUE,
                {"parent": parent_node, "child": child},
            )
        linked = True

    result = HierarchyResult(
        shape=shape,
        parent=parent_number,
        children=planned_children,
        linked=linked,
    )
    _persist(state, result)
    return result


def recover_hierarchy(github_issue) -> HierarchyResult:
    """Rebuild hierarchy from a GitHub Issue payload. TaskState is not used."""
    if not isinstance(github_issue, dict):
        return HierarchyResult(shape=())
    parent = _positive(
        (github_issue.get("parent") or {}).get("number")
        if isinstance(github_issue.get("parent"), dict)
        else github_issue.get("number")
    )
    children: list[int] = []
    sub = github_issue.get("subIssues") or github_issue.get("sub_issues") or {}
    nodes = sub.get("nodes") if isinstance(sub, dict) else sub
    for node in nodes or ():
        number = None
        if isinstance(node, dict):
            number = _positive(node.get("number"))
        else:
            number = _positive(node)
        if number is not None:
            children.append(number)
    return HierarchyResult(
        shape=(),
        parent=parent,
        children=tuple(children),
    )


def _allows_children(shape: tuple[str, ...]) -> bool:
    return len(shape) > 1


def _useful_deliverables(values: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (values or ()) if str(item).strip())


def _normalize(value: str) -> str:
    return (value or "").strip().lower()


def _positive(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number < 1:
        return None
    return number


def _graphql_id(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.isdigit():
        return None
    return text


def _persist(state: TaskState | None, result: HierarchyResult) -> None:
    if state is None or result.parent is None:
        return
    state.issue = result.parent
