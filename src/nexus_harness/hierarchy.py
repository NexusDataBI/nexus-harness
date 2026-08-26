"""Minimal GitHub Issue hierarchy — no Jira-style ceremony.

Bounded bugs/improvements stay one Issue. Epic → Feature → Task is only the
shape for architectural/long-horizon features. Empty child Issues are never
created to fill that shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from nexus_harness.state import TaskState

_BUG_TYPES = frozenset({"bug", "bugfix"})
_FEATURE_TYPES = frozenset({"feature", "story"})
_ARCHITECTURAL_SCOPES = frozenset({"architectural", "long-horizon", "longhorizon"})

_ADD_SUB_ISSUE = """
mutation($parent: Int!, $child: Int!, $repo: String!) {
  addSubIssue(input: { issueId: $parent, subIssueId: $child }) {
    issue { number }
    subIssue { number }
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
    linked = False
    if authorize_remote_mutation and parent_number is not None and planned_children:
        for child in planned_children:
            github.api_graphql(
                _ADD_SUB_ISSUE,
                {"parent": parent_number, "child": child, "repo": repo},
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


def _persist(state: TaskState | None, result: HierarchyResult) -> None:
    if state is None or result.parent is None:
        return
    state.issue = result.parent
    state.parent_issue = result.parent
    state.child_issues = result.children
