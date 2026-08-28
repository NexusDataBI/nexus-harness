"""Canonical repository identity for CI and local execution.

Separates the git checkout (often a GitHub ``pull_request`` merge ref) from
the proposed change head. Freshness for change-bound evidence uses
``change_head_sha``, never an untrusted environment override.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_PR_EVENTS = frozenset(
    {
        "pull_request",
        "pull_request_review",
        "pull_request_review_comment",
    }
)
_FORBIDDEN_EVENTS = frozenset({"pull_request_target"})


class IdentityError(ValueError):
    """Raised when authoritative change identity cannot be established."""


@dataclass(frozen=True)
class RepoIdentity:
    checkout_sha: str
    change_head_sha: str
    base_sha: str | None = None
    merge_sha: str | None = None
    event_name: str | None = None
    is_fork: bool = False

    @property
    def freshness_target(self) -> str:
        return self.change_head_sha


def resolve_repo_identity(
    env: Mapping[str, str] | None = None,
    *,
    git_head: str | None = None,
    event: Mapping[str, Any] | None = None,
    cwd: Path | str | None = None,
) -> RepoIdentity:
    """Resolve checkout vs change-head identity. Fail closed in PR context."""
    environ = {str(key): str(value) for key, value in dict(env or {}).items()}
    event_name = (environ.get("GITHUB_EVENT_NAME") or "").strip().lower()
    if event_name in _FORBIDDEN_EVENTS:
        raise IdentityError(
            f"{event_name} is not a trusted change-head context; fail closed"
        )

    payload = _load_event(environ, event)

    if event_name in _PR_EVENTS:
        return _from_pull_request(environ, payload, git_head=git_head, cwd=cwd)

    if event_name == "push":
        return _from_push(environ, payload, git_head=git_head, cwd=cwd)

    checkout = _checkout_sha(environ, git_head=git_head, cwd=cwd)
    return RepoIdentity(
        checkout_sha=checkout,
        change_head_sha=checkout,
        event_name=event_name or None,
    )


def _from_pull_request(
    environ: Mapping[str, str],
    payload: Mapping[str, Any] | None,
    *,
    git_head: str | None,
    cwd: Path | str | None,
) -> RepoIdentity:
    if payload is None:
        raise IdentityError("pull_request context is missing the event payload")
    pull = payload.get("pull_request")
    if not isinstance(pull, Mapping):
        raise IdentityError("pull_request payload is missing pull_request")
    head = pull.get("head")
    if not isinstance(head, Mapping):
        raise IdentityError("authoritative pull_request.head is missing")
    change_head = _sha(head.get("sha"), field="pull_request.head.sha")
    base = pull.get("base")
    base_sha = None
    if isinstance(base, Mapping) and base.get("sha"):
        base_sha = _sha(base.get("sha"), field="pull_request.base.sha")
    checkout = _checkout_sha(environ, git_head=git_head, cwd=cwd)
    is_fork = False
    repo = head.get("repo")
    if isinstance(repo, Mapping):
        is_fork = bool(repo.get("fork"))
    merge_raw = pull.get("merge_commit_sha")
    merge_sha = None
    if merge_raw:
        merge_sha = _sha(merge_raw, field="pull_request.merge_commit_sha")
    elif checkout != change_head:
        merge_sha = checkout
    return RepoIdentity(
        checkout_sha=checkout,
        change_head_sha=change_head,
        base_sha=base_sha,
        merge_sha=merge_sha,
        event_name="pull_request",
        is_fork=is_fork,
    )


def _from_push(
    environ: Mapping[str, str],
    payload: Mapping[str, Any] | None,
    *,
    git_head: str | None,
    cwd: Path | str | None,
) -> RepoIdentity:
    checkout = _checkout_sha(environ, git_head=git_head, cwd=cwd)
    change_head = None
    if isinstance(payload, Mapping):
        after = payload.get("after")
        if after:
            change_head = _sha(after, field="push.after")
        else:
            commit = payload.get("head_commit")
            if isinstance(commit, Mapping) and commit.get("id"):
                change_head = _sha(commit.get("id"), field="push.head_commit.id")
    if change_head is None:
        github_sha = (environ.get("GITHUB_SHA") or "").strip()
        if github_sha:
            change_head = _sha(github_sha, field="GITHUB_SHA")
        else:
            change_head = checkout
    return RepoIdentity(
        checkout_sha=checkout,
        change_head_sha=change_head,
        event_name="push",
    )


def _checkout_sha(
    environ: Mapping[str, str],
    *,
    git_head: str | None,
    cwd: Path | str | None,
) -> str:
    if git_head:
        return _sha(git_head, field="git_head")
    github_sha = (environ.get("GITHUB_SHA") or "").strip()
    if github_sha:
        return _sha(github_sha, field="GITHUB_SHA")
    completed = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return _sha((completed.stdout or "").strip(), field="git_head")


def _load_event(
    environ: Mapping[str, str],
    event: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if event is not None:
        if not isinstance(event, Mapping):
            raise IdentityError("event payload is not a mapping")
        return dict(event)
    path = (environ.get("GITHUB_EVENT_PATH") or "").strip()
    if not path:
        return None
    event_file = Path(path)
    if not event_file.is_file() or event_file.is_symlink():
        raise IdentityError("GITHUB_EVENT_PATH is not a readable file")
    try:
        payload = json.loads(event_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityError("GITHUB_EVENT_PATH is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise IdentityError("event payload is not a mapping")
    return payload


def _sha(value: object, *, field: str) -> str:
    text = str(value or "").strip().lower()
    if not _SHA.fullmatch(text) or set(text) == {"0"}:
        raise IdentityError(f"invalid {field}")
    return text
