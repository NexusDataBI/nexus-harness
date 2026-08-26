"""Render a short, derived PROJECT.md for agent orientation.

Identity comes from Project registry records. GitHub Issues, PRs, Project
and git history remain operational truth. Secrets, VM IPs, SSH material
and private machine paths are never written.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from string import Template
import re

from nexus_harness.config import load_toml
from nexus_harness.project import Project, ProjectRegistry
from nexus_harness.quality import load_quality_profile
from nexus_harness.runtime_common import generated_markdown


DEFAULT_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "PROJECT.md"
DEFAULT_PROFILE = Path(__file__).resolve().parents[2] / "profiles" / "default.toml"
DEFAULT_FOCUS = "See open Issues and the GitHub Project. This file is not the backlog."
DEFAULT_LINKS = "None declared. See repository docs and GitHub."

_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
_IPV6 = re.compile(r"(?i)\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f:.]*[0-9a-f]\b")
_SSH = re.compile(
    r"(?i)(?:\b(?:ssh|scp)://[^\s\"'<>]+"
    r"|\b(?:ssh|scp)\s+[A-Za-z0-9._-]+@[A-Za-z0-9.-]+(?::[^\s\"'<>]+)?)"
)
_ABS_PATH = re.compile(r"(?:/Users/[^\s\"']+|/home/[^\s\"']+|[A-Za-z]:\\[^\s\"']+)")
_SECRET = re.compile(
    r"(?i)("
    r"ghp_[A-Za-z0-9_]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|ghs_[A-Za-z0-9_]{20,}"
    r"|gho_[A-Za-z0-9_]{20,}"
    r"|ghu_[A-Za-z0-9_]{20,}"
    r"|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
    r")"
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RELATIVE_LINK = re.compile(r"^(?!\.\.)[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")


def render_project_doc(
    project: Project,
    profile: Mapping | Path | None = None,
    *,
    current_focus: str = "",
    template_path: Path | None = None,
) -> str:
    values = _template_values(project, _as_profile(profile), current_focus)
    template = Template(_load_template(template_path))
    return generated_markdown(template.substitute(values))


def generate_project_doc(
    project_id: str,
    *,
    registry: ProjectRegistry | None = None,
    profile: Mapping | Path | None = None,
    current_focus: str = "",
    template_path: Path | None = None,
) -> str:
    source = registry or ProjectRegistry.load()
    return render_project_doc(
        source.by_id(project_id),
        profile,
        current_focus=current_focus,
        template_path=template_path,
    )


def _template_values(
    project: Project,
    profile: Mapping,
    current_focus: str,
) -> dict[str, str]:
    meta = _section(profile, "profile")
    runtime = _section(profile, "runtime")
    observability = _section(profile, "observability")
    return {
        "id": project.id,
        "name": project.name.strip() or project.id,
        "repository": project.repository,
        "client": project.client,
        "status": project.status,
        "current_focus": _safe_text(current_focus, DEFAULT_FOCUS),
        "runtime_name": _safe_id(meta.get("name"), "default"),
        "prefer_local_execution": _flag(runtime.get("prefer_local_execution"), "true"),
        "ci_compute": _safe_id(runtime.get("ci_compute"), "self_hosted"),
        "production_access": _safe_id(
            runtime.get("production_access"), "never_implicit"
        ),
        "quality_profile": _quality_name(meta.get("quality_profile")),
        "observability_id": _safe_id(observability.get("id"), project.id),
        "commands": _commands(profile),
        "architecture_links": _architecture_links(profile),
    }


def _as_profile(profile: Mapping | Path | None) -> dict:
    if profile is None:
        if DEFAULT_PROFILE.is_file():
            return load_toml(DEFAULT_PROFILE)
        return {}
    if isinstance(profile, Path):
        return load_toml(profile)
    if isinstance(profile, Mapping):
        return dict(profile)
    raise TypeError("profile must be a mapping or path")


def _load_template(path: Path | None) -> str:
    source = path or DEFAULT_TEMPLATE
    return source.read_text(encoding="utf-8")


def _section(profile: Mapping, name: str) -> Mapping:
    raw = profile.get(name)
    return raw if isinstance(raw, Mapping) else {}


def _commands(profile: Mapping) -> str:
    table = _section(profile, "commands") or _section(profile, "checks")
    lines: list[str] = []
    for key in sorted(table):
        name = str(key)
        value = _safe_text(table[key])
        if not _SAFE_ID.match(name) or not value or not _SAFE_ID.match(value):
            continue
        lines.append(f"- `{name}`: `{value}`")
    return "\n".join(lines) if lines else "None declared."


def _architecture_links(profile: Mapping) -> str:
    raw = _section(profile, "architecture").get("links")
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    links: list[str] = []
    for item in items:
        text = str(item).strip()
        if _RELATIVE_LINK.match(text) and not _is_unsafe(text):
            links.append(text)
    unique = sorted(set(links))
    if not unique:
        return DEFAULT_LINKS
    return "\n".join(f"- `{link}`" for link in unique)


def _quality_name(value: object) -> str:
    name = _safe_id(value, "standard")
    try:
        load_quality_profile(name)
    except ValueError:
        return "standard"
    return name


def _flag(value: object, fallback: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return _safe_id(value, fallback)


def _safe_id(value: object, fallback: str) -> str:
    text = _safe_text(value, fallback)
    if text and _SAFE_ID.match(text):
        return text
    return fallback


def _safe_text(value: object, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    if not text or _is_unsafe(text):
        return fallback
    return text


def _is_unsafe(text: str) -> bool:
    return bool(
        _IPV4.search(text)
        or _IPV6.search(text)
        or _SSH.search(text)
        or _ABS_PATH.search(text)
        or _SECRET.search(text)
    )
