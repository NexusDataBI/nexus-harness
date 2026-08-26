"""Typed GitHub CLI/API boundary.

Every ``gh`` invocation is an argv list with ``shell=False``. Issue title/body
are never concatenated into a shell string. Errors include the GitHub message
but redact tokens and never dump the process environment.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from nexus_harness.project import canonicalize_repository


class GitHubError(RuntimeError):
    """Raised when a ``gh`` command fails or returns unusable output."""


@dataclass(frozen=True)
class Issue:
    number: int
    url: str = ""
    title: str = ""
    state: str = ""


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str = ""
    title: str = ""
    state: str = ""
    is_draft: bool = False


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:GH_TOKEN|GITHUB_TOKEN|PAT\b|Authorization)\s*[:=]\s*.+"
)
_BEARER = re.compile(r"(?i)\bBearer\s+\S+")
_GITHUB_TOKEN_VALUE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+)\b"
)
_ENV_DUMP_LINE = re.compile(
    r"(?i)(?:env(?:ironment)?\s*dump\b|GH_TOKEN=|GITHUB_TOKEN="
    r"|\bPAT=|Authorization\s*:)"
)
_ISSUE_URL = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/issues/(\d+)")
_PR_URL = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/pull/(\d+)")
_EDIT_FIELDS = frozenset({"title", "body", "add_label", "remove_label"})


class GitHub:
    """Thin ``gh`` wrapper for Issue, PR and Project operations."""

    def create_issue(
        self,
        repo: str,
        title: str,
        body: str,
        labels: Sequence[str] | None = None,
    ) -> Issue:
        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            _repo(repo),
            "--title",
            title,
            "--body",
            body,
        ]
        for label in labels or ():
            cmd.extend(["--label", str(label)])
        return _issue_from_stdout(_run(cmd))

    def edit_issue(self, repo: str, number: int, **fields: Any) -> Issue:
        unknown = set(fields) - _EDIT_FIELDS
        if unknown:
            raise GitHubError(f"unsupported edit fields: {', '.join(sorted(unknown))}")
        cmd = ["gh", "issue", "edit", str(number), "--repo", _repo(repo)]
        if "title" in fields:
            cmd.extend(["--title", str(fields["title"])])
        if "body" in fields:
            cmd.extend(["--body", str(fields["body"])])
        for label in _as_values(fields.get("add_label")):
            cmd.extend(["--add-label", label])
        for label in _as_values(fields.get("remove_label")):
            cmd.extend(["--remove-label", label])
        return _issue_from_stdout(_run(cmd), fallback_number=int(number))

    def view_issue(self, repo: str, number: int) -> Issue:
        cmd = [
            "gh",
            "issue",
            "view",
            str(number),
            "--repo",
            _repo(repo),
            "--json",
            "number,url,title,state",
        ]
        return _issue_from_stdout(_run(cmd), fallback_number=int(number))

    def find_issue(self, repo: str, query: str) -> Issue | None:
        cmd = [
            "gh",
            "issue",
            "list",
            "--repo",
            _repo(repo),
            "--search",
            query,
            "--state",
            "open",
            "--json",
            "number,url,title,state",
            "--limit",
            "1",
        ]
        payload = _parse_json(_run(cmd))
        if payload in (None, [], {}):
            return None
        if isinstance(payload, list):
            if not payload:
                return None
            return _issue_from_payload(payload[0])
        return _issue_from_payload(payload)

    def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        *,
        base: str | None = None,
        head: str | None = None,
        draft: bool = False,
    ) -> PullRequest:
        cmd = [
            "gh",
            "pr",
            "create",
            "--repo",
            _repo(repo),
            "--title",
            title,
            "--body",
            body,
        ]
        if base:
            cmd.extend(["--base", base])
        if head:
            cmd.extend(["--head", head])
        if draft:
            cmd.append("--draft")
        return _pr_from_stdout(_run(cmd))

    def view_pr(self, repo: str, number: int) -> PullRequest:
        cmd = [
            "gh",
            "pr",
            "view",
            str(number),
            "--repo",
            _repo(repo),
            "--json",
            "number,url,title,state,isDraft",
        ]
        return _pr_from_payload(_parse_json(_run(cmd)))

    def api_graphql(
        self,
        query: str,
        variables: Mapping[str, Any] | None = None,
    ) -> Any:
        cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
        for key, value in (variables or {}).items():
            flag = "-f" if isinstance(value, str) else "-F"
            encoded = value if isinstance(value, str) else json.dumps(value)
            cmd.extend([flag, f"{key}={encoded}"])
        return _parse_json(_run(cmd))

    def project_item_update(
        self,
        item_id: str,
        project_id: str,
        field_id: str,
        *,
        text: str | None = None,
        number: float | None = None,
        single_select_option_id: str | None = None,
        date: str | None = None,
        iteration_id: str | None = None,
        clear: bool = False,
    ) -> Any:
        cmd = [
            "gh",
            "project",
            "item-edit",
            "--id",
            item_id,
            "--project-id",
            project_id,
            "--field-id",
            field_id,
            "--format",
            "json",
        ]
        if clear:
            cmd.append("--clear")
        elif text is not None:
            cmd.extend(["--text", text])
        elif number is not None:
            cmd.extend(["--number", str(number)])
        elif single_select_option_id is not None:
            cmd.extend(["--single-select-option-id", single_select_option_id])
        elif date is not None:
            cmd.extend(["--date", date])
        elif iteration_id is not None:
            cmd.extend(["--iteration-id", iteration_id])
        else:
            raise GitHubError("project_item_update requires a field value")
        return _parse_json(_run(cmd))


def _repo(value: str) -> str:
    try:
        return canonicalize_repository(value)
    except ValueError as exc:
        raise GitHubError(str(exc)) from exc


def _run(argv: Sequence[str]) -> str:
    cmd = [str(part) for part in argv]
    try:
        completed = subprocess.run(  # noqa: S603
            cmd,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise GitHubError("gh CLI is not available") from exc
    except OSError as exc:
        raise GitHubError(_redact(f"gh execution failed: {exc}")) from None
    if completed.returncode != 0:
        raise GitHubError(
            _error_message(completed.returncode, completed.stderr, completed.stdout)
        )
    return completed.stdout or ""


def _error_message(returncode: int, stderr: str, stdout: str) -> str:
    detail = _sanitize_output(stderr) or _sanitize_output(stdout) or "gh command failed"
    return f"gh failed (exit {returncode}): {detail}"


def _sanitize_output(text: str) -> str:
    kept: list[str] = []
    for line in (text or "").splitlines():
        if _ENV_DUMP_LINE.search(line):
            continue
        redacted = _redact(line).strip()
        if redacted:
            kept.append(redacted)
    return "\n".join(kept)


def _redact(text: str) -> str:
    text = _SECRET_ASSIGNMENT.sub("[redacted]", text)
    text = _BEARER.sub("[redacted]", text)
    return _GITHUB_TOKEN_VALUE.sub("[redacted]", text)


def _parse_json(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GitHubError(_redact(f"invalid gh JSON: {text[:200]}")) from exc


def _issue_from_stdout(stdout: str, *, fallback_number: int | None = None) -> Issue:
    text = stdout.strip()
    payload = _maybe_json(text)
    if payload is not None:
        if isinstance(payload, list):
            if not payload:
                raise GitHubError("gh JSON listed no issues")
            payload = payload[0]
        return _issue_from_payload(payload)
    match = _ISSUE_URL.search(text)
    if match:
        return Issue(number=int(match.group(1)), url=match.group(0))
    if fallback_number is not None:
        return Issue(number=int(fallback_number), url=text.split()[0] if text else "")
    raise GitHubError(_redact("unusable gh issue output"))


def _pr_from_stdout(stdout: str) -> PullRequest:
    text = stdout.strip()
    payload = _maybe_json(text)
    if payload is not None:
        return _pr_from_payload(payload)
    match = _PR_URL.search(text)
    if match:
        return PullRequest(number=int(match.group(1)), url=match.group(0))
    raise GitHubError(_redact("unusable gh pull request output"))


def _maybe_json(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    return _parse_json(stripped)


def _issue_from_payload(payload: object) -> Issue:
    if not isinstance(payload, dict) or "number" not in payload:
        raise GitHubError("gh JSON missing issue number")
    return Issue(
        number=int(payload["number"]),
        url=str(payload.get("url") or ""),
        title=str(payload.get("title") or ""),
        state=str(payload.get("state") or ""),
    )


def _pr_from_payload(payload: object) -> PullRequest:
    if not isinstance(payload, dict) or "number" not in payload:
        raise GitHubError("gh JSON missing pull request number")
    draft = payload.get("isDraft", payload.get("is_draft", False))
    return PullRequest(
        number=int(payload["number"]),
        url=str(payload.get("url") or ""),
        title=str(payload.get("title") or ""),
        state=str(payload.get("state") or ""),
        is_draft=bool(draft),
    )


def _as_values(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return (str(value),)
