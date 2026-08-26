"""Resolve CI checks/images from changed paths via a component graph."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

from nexus_harness.config import load_toml


@dataclass(frozen=True)
class Component:
    name: str
    paths: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()
    images: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class AffectedPlan:
    components: tuple[str, ...]
    checks: tuple[str, ...]
    images: tuple[str, ...]
    unmatched: tuple[str, ...] = ()


@dataclass(frozen=True)
class CiProfile:
    project_id: str
    repository: str
    components: tuple[Component, ...]
    global_paths: tuple[str, ...] = ()


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a simple **/* glob into an anchored regex."""
    escaped: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            escaped.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            escaped.append(".*")
            i += 2
        elif pattern[i] == "*":
            escaped.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            escaped.append("[^/]")
            i += 1
        else:
            escaped.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(escaped) + "$")


def path_matches(changed_path: str, pattern: str) -> bool:
    normalized = changed_path.lstrip("./")
    return _glob_to_regex(pattern).match(normalized) is not None


def _any_match(changed_path: str, patterns: Sequence[str]) -> bool:
    return any(path_matches(changed_path, pattern) for pattern in patterns)


def _component_matches(changed_path: str, component: Component) -> bool:
    if component.exclude and _any_match(changed_path, component.exclude):
        return False
    return _any_match(changed_path, component.paths)


def resolve_affected(
    changed_paths: Sequence[str],
    components: Sequence[Component],
    *,
    global_paths: Sequence[str] = (),
) -> AffectedPlan:
    """Map changed paths to affected components, checks, and images.

    Unknown/non-global paths never expand to the full monorepo. Only
    ``global_paths`` (fail-closed critical files) mark every component.
    Dependents are closed transitively via ``depends_on``.
    Paths matching a component's ``exclude`` do not select that component.
    """
    by_name = {component.name: component for component in components}
    affected: set[str] = set()
    unmatched: list[str] = []

    for changed in changed_paths:
        if global_paths and _any_match(changed, global_paths):
            affected.update(by_name)
            continue

        matched = False
        for component in components:
            if _component_matches(changed, component):
                affected.add(component.name)
                matched = True
        if not matched:
            unmatched.append(changed)

    # Transitive dependents: if A depends_on B and B is affected, A is affected.
    changed = True
    while changed:
        changed = False
        for component in components:
            if component.name in affected:
                continue
            if any(dep in affected for dep in component.depends_on):
                affected.add(component.name)
                changed = True

    ordered = tuple(c.name for c in components if c.name in affected)
    checks: list[str] = []
    images: list[str] = []
    seen_checks: set[str] = set()
    seen_images: set[str] = set()
    for name in ordered:
        component = by_name[name]
        for check in component.checks:
            if check not in seen_checks:
                seen_checks.add(check)
                checks.append(check)
        for image in component.images:
            if image not in seen_images:
                seen_images.add(image)
                images.append(image)

    return AffectedPlan(
        components=ordered,
        checks=tuple(checks),
        images=tuple(images),
        unmatched=tuple(unmatched),
    )


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    raise TypeError(f"expected string list, got {type(value)!r}")


def _resolve_global_paths(data: dict, project: dict) -> tuple[str, ...]:
    """Read fail-closed paths from root or ``[project]``; conflict → raise."""
    top = _as_str_tuple(data.get("global_paths"))
    if not top:
        top = _as_str_tuple(data.get("fail_closed_paths"))

    nested = _as_str_tuple(project.get("global_paths"))
    if not nested:
        nested = _as_str_tuple(project.get("fail_closed_paths"))

    if top and nested and top != nested:
        raise ValueError(
            "conflicting global_paths: top-level and project-level differ "
            f"({top!r} vs {nested!r})"
        )
    return top or nested


def load_ci_profile(path: Path | str) -> CiProfile:
    """Load a data-driven CI profile (components + fail-closed global paths)."""
    data = load_toml(Path(path))
    project = data.get("project") or {}
    project_id = str(project.get("id") or "")
    repository = str(project.get("repository") or "")

    raw_components = data.get("components") or {}
    components: list[Component] = []
    for name, raw in raw_components.items():
        if not isinstance(raw, dict):
            raise TypeError(f"component {name!r} must be a table")
        components.append(
            Component(
                name=str(name),
                paths=_as_str_tuple(raw.get("paths")),
                depends_on=_as_str_tuple(raw.get("depends_on")),
                checks=_as_str_tuple(raw.get("checks")),
                images=_as_str_tuple(raw.get("images")),
                exclude=_as_str_tuple(raw.get("exclude")),
            )
        )

    global_paths = _resolve_global_paths(
        data, project if isinstance(project, dict) else {}
    )

    return CiProfile(
        project_id=project_id,
        repository=repository,
        components=tuple(components),
        global_paths=global_paths,
    )


# Convenience for callers that only need the component list.
def load_ci_components(path: Path | str) -> list[Component]:
    return list(load_ci_profile(path).components)
