"""Cross-repository project identity registry.

Loads non-secret identity only. Lookups accept safe GitHub forms
(``owner/repo``, ``https://github.com/owner/repo``, optional ``.git``)
without treating unrelated hosts or paths as the same repository.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlparse

from nexus_harness.config import load_toml

ALLOWED_FIELDS = frozenset({"id", "name", "repository", "client", "status"})
REQUIRED_FIELDS = ("repository", "client", "status")
ALLOWED_STATUSES = frozenset({"active", "paused", "archived"})
_SEGMENT_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
DEFAULT_PROJECTS_TOML = Path(__file__).resolve().parents[2] / "projects.toml"


class ProjectRegistryError(ValueError):
    """Invalid project registry document or lookup."""


@dataclass(frozen=True)
class Project:
    id: str
    repository: str
    client: str
    status: str
    name: str = ""


@dataclass(frozen=True)
class ProjectRegistry:
    _by_id: Mapping[str, Project]
    _by_repository: Mapping[str, Project]

    @classmethod
    def from_dict(cls, payload: object) -> ProjectRegistry:
        if not isinstance(payload, dict):
            raise ProjectRegistryError("registry must be an object")
        extra_top = set(payload) - {"projects"}
        if extra_top:
            raise ProjectRegistryError(
                f"unknown registry fields: {', '.join(sorted(extra_top))}"
            )
        if "projects" not in payload:
            raise ProjectRegistryError("missing projects")
        raw_projects = payload["projects"]
        if not isinstance(raw_projects, dict):
            raise ProjectRegistryError("projects must be an object")

        by_id: dict[str, Project] = {}
        by_repository: dict[str, Project] = {}
        for key, raw in raw_projects.items():
            project = _project_from_entry(key, raw)
            if project.id in by_id:
                raise ProjectRegistryError(f"duplicate project id: {project.id}")
            if project.repository in by_repository:
                raise ProjectRegistryError(
                    f"duplicate repository: {project.repository}"
                )
            by_id[project.id] = project
            by_repository[project.repository] = project
        return cls(
            _by_id=MappingProxyType(by_id),
            _by_repository=MappingProxyType(by_repository),
        )

    @classmethod
    def from_path(cls, path: Path) -> ProjectRegistry:
        try:
            payload = load_toml(Path(path))
        except (OSError, ValueError) as exc:
            raise ProjectRegistryError(f"cannot load projects: {exc}") from exc
        return cls.from_dict(payload)

    @classmethod
    def load(cls, path: Path | None = None) -> ProjectRegistry:
        return cls.from_path(path or DEFAULT_PROJECTS_TOML)

    def by_id(self, project_id: str) -> Project:
        key = _required_text(project_id, "id")
        try:
            return self._by_id[key]
        except KeyError as exc:
            raise ProjectRegistryError(f"unknown project id: {key}") from exc

    def by_repository(self, repository: str) -> Project:
        key = canonicalize_repository(repository)
        try:
            return self._by_repository[key]
        except KeyError as exc:
            raise ProjectRegistryError(f"unknown repository: {key}") from exc


def canonicalize_repository(value: object) -> str:
    text = _required_text(value, "repository")
    if "://" in text or text.startswith("//"):
        return _from_https_github(text)
    if text.startswith("git@"):
        raise ProjectRegistryError("unsupported repository form")
    return _owner_repo(_strip_git_suffix(text))


def _project_from_entry(key: object, raw: object) -> Project:
    project_id = _required_text(key, "id")
    if not isinstance(raw, dict):
        raise ProjectRegistryError(f"project {project_id} must be an object")
    extra = set(raw) - ALLOWED_FIELDS
    if extra:
        raise ProjectRegistryError(
            f"unknown fields for {project_id}: {', '.join(sorted(extra))}"
        )
    if "id" in raw:
        declared = _required_text(raw["id"], "id")
        if declared != project_id:
            raise ProjectRegistryError(
                f"id field '{declared}' does not match key '{project_id}'"
            )
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise ProjectRegistryError(
            f"missing fields for {project_id}: {', '.join(missing)}"
        )
    name = raw["name"] if "name" in raw else ""
    if name is None:
        name = ""
    if not isinstance(name, str):
        raise ProjectRegistryError(f"invalid name for {project_id}")
    status = _required_text(raw["status"], "status")
    if status not in ALLOWED_STATUSES:
        raise ProjectRegistryError(f"invalid status for {project_id}: {status}")
    return Project(
        id=project_id,
        repository=canonicalize_repository(raw["repository"]),
        client=_required_text(raw["client"], "client"),
        status=status,
        name=name.strip(),
    )


def _from_https_github(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise ProjectRegistryError("unsupported repository form")
    if parsed.username or parsed.password:
        raise ProjectRegistryError("repository URL must not contain credentials")
    if parsed.hostname is None or parsed.hostname.lower() != "github.com":
        raise ProjectRegistryError("unsupported repository host")
    if parsed.port is not None:
        raise ProjectRegistryError("unsupported repository form")
    if parsed.query or parsed.fragment or parsed.params:
        raise ProjectRegistryError("unsupported repository form")
    path = parsed.path.strip("/")
    return _owner_repo(_strip_git_suffix(path))


def _strip_git_suffix(path: str) -> str:
    if path.endswith(".git"):
        return path[: -len(".git")]
    return path


def _owner_repo(path: str) -> str:
    parts = path.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ProjectRegistryError("repository must be owner/repo")
    owner, repo = parts
    if not _valid_segment(owner) or not _valid_segment(repo):
        raise ProjectRegistryError("invalid repository identity")
    return f"{owner}/{repo}"


def _valid_segment(value: str) -> bool:
    if value in {".", ".."}:
        return False
    return bool(value) and all(char in _SEGMENT_CHARS for char in value)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ProjectRegistryError(f"{label} is required")
    text = value.strip()
    if not text:
        raise ProjectRegistryError(f"{label} is required")
    return text
