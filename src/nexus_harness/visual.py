"""Visual evidence freshness, viewport requirements, and runtime policy.

Freshness reuses Plan 2 Evidence semantics: ``diff_hash == current_diff_hash``.
Material visual requirement reuses ``affected.path_matches`` against
``visual_paths``. This module does not invent a second Done Gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Sequence

from nexus_harness.affected import path_matches
from nexus_harness.safe import confine

REQUIRED_VIEWPORTS = ("desktop", "mobile")
SKIP_KINDS = frozenset({"type_only", "test_only", "no_render"})
DEFAULT_LIMITATION = (
    "Screenshots and traces may contain runtime data. "
    "Do not put tokens, cookies, or Authorization headers in summaries."
)
DEFAULT_CONSOLE_ALLOWLIST = (
    "Download the React DevTools",
    "[HMR]",
    "[webpack-dev-server]",
    "Fast Refresh",
)
DEFAULT_NETWORK_ALLOWLIST = (
    "/_next/webpack-hmr",
    "/__webpack_hmr",
)

_FRONTEND_POLICY = (
    Path(__file__).resolve().parents[2] / "core" / "quality" / "frontend.toml"
)


@dataclass(frozen=True)
class VisualEvidence:
    route: str
    viewport: str
    diff_hash: str
    screenshot: str | None = None
    baseline: str | None = None
    baseline_missing_reason: str | None = None
    trace: str | None = None
    console_error_count: int = 0
    failed_request_count: int = 0
    reviewer_status: str | None = None
    console_messages: tuple[str, ...] = ()
    failed_request_urls: tuple[str, ...] = ()
    limitation: str | None = DEFAULT_LIMITATION
    base_commit: str = ""
    attempt_ok: bool = True
    captured_at: str | None = None

    def is_fresh(self, current_diff_hash: str) -> bool:
        return self.diff_hash == current_diff_hash


@dataclass(frozen=True)
class VisualPolicy:
    required_viewports: tuple[str, ...] = REQUIRED_VIEWPORTS
    console_allowlist: tuple[str, ...] = DEFAULT_CONSOLE_ALLOWLIST
    network_allowlist: tuple[str, ...] = DEFAULT_NETWORK_ALLOWLIST


def load_visual_policy(path: Path | None = None) -> VisualPolicy:
    source = Path(path) if path is not None else _FRONTEND_POLICY
    data: dict = {}
    if source.is_file():
        with source.open("rb") as handle:
            loaded = tomllib.load(handle)
        if isinstance(loaded, dict):
            data = loaded
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    console = visual.get("console") if isinstance(visual.get("console"), dict) else {}
    network = visual.get("network") if isinstance(visual.get("network"), dict) else {}
    viewports = _str_tuple(visual.get("required_viewports")) or REQUIRED_VIEWPORTS
    console_allow = _str_tuple(console.get("allowlist")) or DEFAULT_CONSOLE_ALLOWLIST
    network_allow = _str_tuple(network.get("allowlist")) or DEFAULT_NETWORK_ALLOWLIST
    return VisualPolicy(
        required_viewports=viewports,
        console_allowlist=console_allow,
        network_allowlist=network_allow,
    )


def is_valid_visual_skip(raw) -> bool:
    if raw is None or isinstance(raw, str):
        return False
    if isinstance(raw, dict):
        kind = str(raw.get("kind") or "").strip()
        reason = str(raw.get("reason") or "").strip()
    else:
        kind = str(getattr(raw, "kind", "") or "").strip()
        reason = str(getattr(raw, "reason", "") or "").strip()
    return kind in SKIP_KINDS and bool(reason)


def matches_visual_paths(
    changed_paths: Sequence[str] | None,
    visual_paths: Sequence[str] | None,
) -> bool:
    return any(
        path_matches(changed, pattern)
        for changed in _str_tuple(changed_paths)
        for pattern in _str_tuple(visual_paths)
    )


def _frontend_visual_paths(frontend) -> tuple[str, ...]:
    if frontend is None:
        return ()
    if isinstance(frontend, dict):
        return _str_tuple(frontend.get("visual_paths"))
    return _str_tuple(getattr(frontend, "visual_paths", None))


def _state_visual_paths(state) -> tuple[str, ...]:
    paths = _str_tuple(_get(state, "visual_paths"))
    if paths:
        return paths
    return _frontend_visual_paths(_get(state, "frontend"))


def is_visual_required(state) -> bool:
    if is_valid_visual_skip(_get(state, "visual_skip")):
        return False
    if _get(state, "visual_required") is True:
        return True
    return matches_visual_paths(
        _get(state, "changed_paths"),
        _state_visual_paths(state),
    )


def bind_visual_requirement(state, profile, changed_paths):
    frontend = None
    if isinstance(profile, dict):
        frontend = profile.get("frontend")
    elif profile is not None:
        frontend = getattr(profile, "frontend", None)
    paths = list(_frontend_visual_paths(frontend))
    changed = [str(item) for item in list(changed_paths or [])]
    if isinstance(state, dict):
        state["visual_paths"] = paths
        state["changed_paths"] = changed
    else:
        state.visual_paths = paths
        state.changed_paths = changed
    return state


def as_visual_evidence(value) -> VisualEvidence | None:
    if value is None:
        return None
    if isinstance(value, VisualEvidence):
        return value
    if not isinstance(value, dict):
        return None
    route = str(value.get("route") or "").strip()
    viewport = str(value.get("viewport") or "").strip()
    if not route or not viewport:
        return None
    limitation = _opt_str(value.get("limitation")) or DEFAULT_LIMITATION
    return VisualEvidence(
        route=route,
        viewport=viewport,
        diff_hash=str(value.get("diff_hash") or ""),
        screenshot=_opt_str(value.get("screenshot")),
        baseline=_opt_str(value.get("baseline")),
        baseline_missing_reason=_opt_str(value.get("baseline_missing_reason")),
        trace=_opt_str(value.get("trace")),
        console_error_count=_as_int(value.get("console_error_count")),
        failed_request_count=_as_int(value.get("failed_request_count")),
        reviewer_status=_opt_str(value.get("reviewer_status")),
        console_messages=_str_tuple(value.get("console_messages")),
        failed_request_urls=_str_tuple(value.get("failed_request_urls")),
        limitation=limitation,
        base_commit=str(value.get("base_commit") or ""),
        attempt_ok=_as_bool(value.get("attempt_ok"), default=True),
        captured_at=_opt_str(value.get("captured_at")),
    )


def runtime_policy_ok(
    evidence: VisualEvidence, policy: VisualPolicy | None = None
) -> bool:
    rules = policy or load_visual_policy()
    if evidence.console_messages:
        if any(
            not _allowlisted(message, rules.console_allowlist)
            for message in evidence.console_messages
        ):
            return False
    elif evidence.console_error_count > 0:
        return False
    if evidence.failed_request_urls:
        if any(
            not _allowlisted(url, rules.network_allowlist)
            for url in evidence.failed_request_urls
        ):
            return False
    elif evidence.failed_request_count > 0:
        return False
    return True


def confine_visual_artifacts(evidence: VisualEvidence, root: Path) -> VisualEvidence:
    """Keep screenshot/trace/baseline paths inside the task evidence root."""
    return VisualEvidence(
        route=evidence.route,
        viewport=evidence.viewport,
        diff_hash=evidence.diff_hash,
        screenshot=_confine_optional(evidence.screenshot, root),
        baseline=_confine_optional(evidence.baseline, root),
        baseline_missing_reason=evidence.baseline_missing_reason,
        trace=_confine_optional(evidence.trace, root),
        console_error_count=evidence.console_error_count,
        failed_request_count=evidence.failed_request_count,
        reviewer_status=evidence.reviewer_status,
        console_messages=evidence.console_messages,
        failed_request_urls=evidence.failed_request_urls,
        limitation=evidence.limitation,
        base_commit=evidence.base_commit,
        attempt_ok=evidence.attempt_ok,
        captured_at=evidence.captured_at,
    )


def visual_completion_reasons(state, current_diff_hash=None) -> list[str]:
    if not is_visual_required(state):
        return []
    current = (
        current_diff_hash
        if current_diff_hash is not None
        else _get(state, "current_diff_hash")
    )
    policy = load_visual_policy()
    items = []
    for raw in _get(state, "visual_evidence") or []:
        record = as_visual_evidence(raw)
        if record is not None:
            items.append(record)

    newest = _newest_attempts(items, current or "")
    ready_viewports: set[str] = set()
    stale = bool(items) and not newest
    runtime_fail = False
    baseline_fail = False
    review_fail = False
    missing_commit = False
    recapture_fail = False
    for evidence in newest:
        if evidence.attempt_ok is False:
            recapture_fail = True
            continue
        if not _opt_str(evidence.screenshot):
            continue
        if not _opt_str(evidence.base_commit):
            missing_commit = True
            continue
        if not _baseline_ok(evidence):
            baseline_fail = True
            continue
        if not runtime_policy_ok(evidence, policy):
            runtime_fail = True
            continue
        if not visual_review_is_pass(evidence):
            review_fail = True
            continue
        ready_viewports.add(evidence.viewport)

    reasons: list[str] = []
    missing = [
        viewport
        for viewport in policy.required_viewports
        if viewport not in ready_viewports
    ]
    if missing:
        reasons.append("missing visual evidence for " + " and ".join(missing))
    if stale:
        reasons.append("visual evidence is not fresh")
    if runtime_fail:
        reasons.append("visual console/network policy failed")
    if baseline_fail:
        reasons.append("visual baseline missing without reason")
    if review_fail:
        reasons.append("visual review is not PASS")
    if missing_commit:
        reasons.append("visual evidence is missing base_commit")
    if recapture_fail:
        reasons.append("visual recapture failed")
    return reasons


def visual_review_is_pass(evidence: VisualEvidence) -> bool:
    """Material visual evidence counts only with an explicit reviewer PASS."""
    return _opt_str(evidence.reviewer_status) == "PASS"


def _baseline_ok(evidence: VisualEvidence) -> bool:
    if _opt_str(evidence.baseline):
        return True
    return bool(_opt_str(evidence.baseline_missing_reason))


def _allowlisted(text: str, patterns: Sequence[str]) -> bool:
    return any(pattern and pattern in text for pattern in patterns)


def _confine_optional(value: str | None, root: Path) -> str | None:
    text = _opt_str(value)
    if text is None:
        return None
    raw = Path(text)
    candidate = raw if raw.is_absolute() else Path(root) / raw
    return str(confine(candidate, root))


def _get(state, key, default=None):
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _opt_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _newest_attempts(
    items: Sequence[VisualEvidence], current_diff_hash: str
) -> list[VisualEvidence]:
    """Newest attempt per (route, viewport) on the current diff wins."""
    groups: dict[tuple[str, str], list[tuple[int, VisualEvidence]]] = {}
    for index, evidence in enumerate(items):
        if not evidence.is_fresh(current_diff_hash):
            continue
        key = (evidence.route, evidence.viewport)
        groups.setdefault(key, []).append((index, evidence))
    newest: list[VisualEvidence] = []
    for ranked in groups.values():
        _index, evidence = max(ranked, key=_attempt_rank)
        newest.append(evidence)
    return newest


def _attempt_rank(item: tuple[int, VisualEvidence]) -> tuple[str, int]:
    index, evidence = item
    return (evidence.captured_at or "", index)


def _as_bool(value, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes"}:
            return True
        if text in {"0", "false", "no"}:
            return False
        return default
    return bool(value)


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _str_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()
