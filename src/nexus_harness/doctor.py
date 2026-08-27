"""Local / release / CI-host doctor. Network-free. No SSH. No live SaaS."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus_harness.affected import load_ci_profile
from nexus_harness.infra import summarize_health
from nexus_harness.memory.doctor import memory_doctor
from nexus_harness.posthog import load_posthog_config
from nexus_harness.project import ProjectRegistry, ProjectRegistryError
from nexus_harness.serialize import observability_doctor_report
from nexus_harness.validate import validate_repository

WhichFn = Callable[[str], str | None]

PYTHON_FLOOR = (3, 11)
PROFILES = frozenset({"local", "release", "ci-host"})
_ACTIONABLE = frozenset({"FAIL", "WARN", "ACTIVATION_REQUIRED"})
_DRIFT_MARKERS = ("drift", "harness.lock")
_ADAPTER_FILES = {
    "claude": ("claude/CLAUDE.md", "claude/settings.json"),
    "cursor": ("USER_RULES.md", ".cursor/rules/nexus-workflow.mdc"),
    "codex": ("AGENTS.md", "codex/config.toml"),
}
_QUALITY_TOOLS = ("biome", "vitest")
_FRONTEND_TOOLS = ("playwright",)
_SECURITY_TOOLS = ("trivy",)


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    required: bool = True
    message: str = ""
    repair: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "required": self.required,
            "message": self.message,
            "repair": self.repair,
        }


@dataclass(frozen=True)
class DoctorReport:
    gate: str
    profile: str = "local"
    checks: tuple[DoctorCheck, ...] = ()
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "profile": self.profile,
            "summary": self.summary,
            "checks": [item.to_dict() for item in self.checks],
        }


def summarize(checks: Sequence[DoctorCheck], *, profile: str = "local") -> DoctorReport:
    """Aggregate checks. ACTIVATION_REQUIRED / SKIP never fail local or release."""
    items = tuple(checks)
    if any(item.status == "FAIL" and item.required for item in items):
        gate = "FAIL"
    elif any(item.status == "WARN" for item in items):
        gate = "WARN"
    else:
        gate = "PASS"
    summary = f"{gate}: " + ", ".join(f"{item.name}={item.status}" for item in items)
    return DoctorReport(gate=gate, profile=profile, checks=items, summary=summary)


def format_doctor_report(report: DoctorReport) -> str:
    lines = [f"nexus doctor [{report.profile}]  gate={report.gate}", ""]
    for check in report.checks:
        lines.append(f"{check.status:20} {check.name}")
        if check.status not in _ACTIONABLE:
            continue
        lines.append(f"  what: {check.name}")
        lines.append(f"  why: {check.message or check.status}")
        label = "activate" if check.status == "ACTIVATION_REQUIRED" else "repair"
        if check.repair:
            lines.append(f"  {label}: {check.repair}")
    return "\n".join(lines) + "\n"


def run_doctor(
    root: Path,
    *,
    profile: str = "local",
    which: WhichFn | None = None,
    python_version: tuple[int, ...] | None = None,
    environ: Mapping[str, str] | None = None,
    adapter_homes: Mapping[str, Path] | None = None,
    runtime_home: Path | None = None,
    ci_facts: Mapping[str, Any] | None = None,
    github_project_ids: Mapping[str, str] | None = None,
    selected_project: str | None = None,
    tools: Mapping[str, bool] | None = None,
) -> DoctorReport:
    if profile not in PROFILES:
        raise ValueError(f"unknown doctor profile: {profile}")
    root = Path(root)
    env = dict(os.environ if environ is None else environ)
    which_fn = which or _default_which
    version = python_version or sys.version_info[:2]
    project_id = selected_project or env.get("NEXUS_DOCTOR_PROJECT") or None
    state_home = runtime_home
    if state_home is None:
        raw = env.get("NEXUS_RUNTIME_HOME")
        state_home = Path(raw) if raw else None

    checks = [
        _check_python(version),
        _check_tool(
            "git",
            which_fn("git"),
            required=True,
            repair="install git (https://git-scm.com/) and ensure it is on PATH",
            missing="git is not on PATH",
        ),
        _check_tool(
            "gh",
            which_fn("gh"),
            required=True,
            missing="GitHub CLI is not on PATH; live GitHub remains Plan 8 activation",
            repair=(
                "install GitHub CLI (`brew install gh` or https://cli.github.com/) "
                "then `gh auth login`. Do not put tokens in git."
            ),
            missing_status="ACTIVATION_REQUIRED",
        ),
        *_check_canonical_and_drift(root),
        *_check_adapters(root, adapter_homes, profile),
        _check_task_state(root, state_home),
        _check_memory(root),
        _check_project_registry(root),
        *_check_project_tools(root, project_id, which_fn, tools),
        _check_ci_profile(profile, ci_facts, root),
        _check_github(env, github_project_ids),
        _check_posthog(root, profile, env),
        _check_release(root),
    ]
    return summarize(checks, profile=profile)


def _default_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def _check_python(version: tuple[int, ...]) -> DoctorCheck:
    major_minor = tuple(version[:2])
    if major_minor >= PYTHON_FLOOR:
        return DoctorCheck(
            "python",
            "PASS",
            message=f"Python {major_minor[0]}.{major_minor[1]} meets floor 3.11",
        )
    return DoctorCheck(
        "python",
        "FAIL",
        message=(
            f"Python {major_minor[0]}.{major_minor[1]} is below the 3.11 floor "
            "(tomllib is required)"
        ),
        repair="install Python 3.11+ (python.org or pyenv) and rerun `scripts/nexus doctor`",
    )


def _check_tool(
    name: str,
    resolved: str | None,
    *,
    required: bool,
    repair: str,
    missing: str,
    missing_status: str = "FAIL",
) -> DoctorCheck:
    if resolved:
        return DoctorCheck(
            name, "PASS", required=required, message=f"{name} → {resolved}"
        )
    return DoctorCheck(
        name,
        missing_status,
        required=required,
        message=missing,
        repair=repair,
    )


def _check_canonical_and_drift(root: Path) -> tuple[DoctorCheck, DoctorCheck]:
    result = validate_repository(root)
    drift: list[str] = []
    core: list[str] = []
    for error in result.errors:
        if any(marker in error.casefold() for marker in _DRIFT_MARKERS):
            drift.append(error)
        else:
            core.append(error)
    canonical = (
        DoctorCheck("canonical-core", "PASS", message="canonical tree validated")
        if not core
        else DoctorCheck(
            "canonical-core",
            "FAIL",
            message="; ".join(core),
            repair="scripts/nexus validate  (see core/, skills/, profiles/, upstream/vendor-lock.json)",
        )
    )
    generated = (
        DoctorCheck(
            "generated-drift", "PASS", message="generated hashes match harness.lock"
        )
        if not drift
        else DoctorCheck(
            "generated-drift",
            "FAIL",
            message="; ".join(drift),
            repair="scripts/nexus build",
        )
    )
    return canonical, generated


def _check_adapters(
    root: Path, adapter_homes: Mapping[str, Path] | None, profile: str
) -> tuple[DoctorCheck, ...]:
    checks: list[DoctorCheck] = []
    dist = root / "dist"
    missing_status = "FAIL" if profile == "release" else "WARN"
    for name, relatives in _ADAPTER_FILES.items():
        missing = [rel for rel in relatives if not (dist / rel).is_file()]
        if missing:
            checks.append(
                DoctorCheck(
                    name,
                    missing_status,
                    message=f"generated {name} adapter missing in dist/: {', '.join(missing)}",
                    repair="scripts/nexus build && scripts/nexus install <dist> <target>",
                )
            )
            continue
        home = adapter_homes.get(name) if adapter_homes else None
        if home is not None and not Path(home).exists():
            checks.append(
                DoctorCheck(
                    name,
                    "ACTIVATION_REQUIRED",
                    message=(
                        f"generated {name} adapter is in dist/; runtime install "
                        f"target {home} is not present (cutover not activated)"
                    ),
                    repair=(
                        "after cutover approval: scripts/nexus install dist "
                        f"{home}  (never overwrite ~/.{name} without backup; "
                        "see docs/operations/cutover.md)"
                    ),
                )
            )
            continue
        checks.append(
            DoctorCheck(
                name,
                "PASS",
                message=f"generated {name} adapter present under dist/",
            )
        )
    return tuple(checks)


def _check_task_state(root: Path, runtime_home: Path | None) -> DoctorCheck:
    targets = [root / ".nexus" / "tasks"]
    if runtime_home is not None:
        targets.append(Path(runtime_home))
    blocked: list[Path] = []
    for path in targets:
        if path.exists() and not os.access(path, os.W_OK):
            blocked.append(path)
    if blocked:
        shown = ", ".join(str(path) for path in blocked)
        return DoctorCheck(
            "task-state",
            "FAIL",
            message=f"task-state directory is not writable: {shown}",
            repair=f"chmod u+w {shown}  (or set NEXUS_RUNTIME_HOME to a writable path)",
        )
    return DoctorCheck(
        "task-state",
        "PASS",
        message="task-state directories are writable or not yet created",
    )


def _check_memory(root: Path) -> DoctorCheck:
    policy = root / "core" / "memory" / "retrieval-policy.toml"
    if not policy.is_file():
        return DoctorCheck(
            "memory",
            "FAIL",
            message="missing core/memory/retrieval-policy.toml",
            repair="restore core/memory/retrieval-policy.toml from the harness canonical tree",
        )
    try:
        from nexus_harness.config import load_toml

        load_toml(policy)
    except (OSError, ValueError) as exc:
        return DoctorCheck(
            "memory",
            "FAIL",
            message=f"cannot parse {policy}: {exc}",
            repair="fix TOML in core/memory/retrieval-policy.toml",
        )
    memory_root = root / ".nexus" / "memory"
    if memory_root.is_dir():
        report = memory_doctor(root)
        if report.gate == "FAIL":
            codes = (
                ", ".join(item.code for item in report.findings)
                or "memory doctor failed"
            )
            return DoctorCheck(
                "memory",
                "FAIL",
                message=codes,
                repair="python3 -m nexus_harness.memory.cli doctor  (see .nexus/memory/)",
            )
    return DoctorCheck("memory", "PASS", message=f"memory policy ok ({policy})")


def _check_project_registry(root: Path) -> DoctorCheck:
    path = root / "projects.toml"
    if not path.is_file():
        return DoctorCheck(
            "project-registry",
            "FAIL",
            message="missing projects.toml",
            repair="create projects.toml with [projects.<id>] repository/client/status",
        )
    try:
        ProjectRegistry.from_path(path)
    except ProjectRegistryError as exc:
        return DoctorCheck(
            "project-registry",
            "FAIL",
            message=str(exc),
            repair="fix projects.toml (allowed fields: id, name, repository, client, status)",
        )
    return DoctorCheck(
        "project-registry",
        "PASS",
        message="loaded projects.toml",
    )


def _check_project_tools(
    root: Path,
    selected_project: str | None,
    which_fn: WhichFn,
    tools: Mapping[str, bool] | None,
) -> tuple[DoctorCheck, DoctorCheck, DoctorCheck]:
    if not selected_project:
        skip = "no selected project; Biome/Vitest/Playwright/Trivy not required"
        return (
            DoctorCheck("quality-tooling", "SKIP", required=False, message=skip),
            DoctorCheck("frontend-tooling", "SKIP", required=False, message=skip),
            DoctorCheck("trivy", "SKIP", required=False, message=skip),
        )
    profile_path = root / "profiles" / "projects" / f"{selected_project}.toml"
    if not profile_path.is_file():
        repair = f"add {profile_path} or pass a known --project id"
        msg = (
            f"selected project {selected_project!r} has no CI profile at {profile_path}"
        )
        return (
            DoctorCheck("quality-tooling", "FAIL", message=msg, repair=repair),
            DoctorCheck("frontend-tooling", "FAIL", message=msg, repair=repair),
            DoctorCheck("trivy", "FAIL", message=msg, repair=repair),
        )
    profile = load_ci_profile(profile_path)
    mentioned = {
        check.casefold()
        for component in profile.components
        for check in component.checks
    }
    return (
        _tool_group(
            "quality-tooling",
            _QUALITY_TOOLS,
            mentioned,
            which_fn,
            tools,
            repair="install @biomejs/biome and vitest as devDependencies (pnpm add -D @biomejs/biome vitest)",
        ),
        _tool_group(
            "frontend-tooling",
            _FRONTEND_TOOLS,
            mentioned,
            which_fn,
            tools,
            repair="install Playwright (`pnpm add -D @playwright/test` then `npx playwright install`)",
        ),
        _tool_group(
            "trivy",
            _SECURITY_TOOLS,
            mentioned,
            which_fn,
            tools,
            repair="install Trivy (https://trivy.dev/) and ensure `trivy` is on PATH",
        ),
    )


def _tool_group(
    name: str,
    needed: Sequence[str],
    mentioned: set[str],
    which_fn: WhichFn,
    tools: Mapping[str, bool] | None,
    *,
    repair: str,
) -> DoctorCheck:
    required = [tool for tool in needed if any(tool in item for item in mentioned)]
    if not required:
        return DoctorCheck(
            name,
            "SKIP",
            required=False,
            message=f"selected project does not require {', '.join(needed)}",
        )
    missing = [tool for tool in required if not _tool_available(tool, which_fn, tools)]
    if missing:
        return DoctorCheck(
            name,
            "FAIL",
            message=f"required tooling missing: {', '.join(missing)}",
            repair=repair,
        )
    return DoctorCheck(
        name,
        "PASS",
        message=f"required tooling present: {', '.join(required)}",
    )


def _tool_available(
    name: str, which_fn: WhichFn, tools: Mapping[str, bool] | None
) -> bool:
    if tools is not None and name in tools:
        return bool(tools[name])
    return which_fn(name) is not None


def _check_ci_profile(
    profile: str, ci_facts: Mapping[str, Any] | None, root: Path
) -> DoctorCheck:
    if profile != "ci-host":
        return DoctorCheck(
            "ci-profile",
            "SKIP",
            required=False,
            message=(
                "live VPS is not probed from local/release doctor (no SSH). "
                "Use `scripts/nexus doctor --profile ci-host` with a fixture."
            ),
        )
    if ci_facts is None:
        return DoctorCheck(
            "ci-profile",
            "ACTIVATION_REQUIRED",
            message=(
                "CI-host facts were not supplied; refusing to SSH or probe a live VPS "
                f"(profiles live under {root / 'profiles'})"
            ),
            repair=(
                "activate the Nexus CI VPS separately and feed summarize_health facts; "
                "do not SSH from doctor. See docs/operations/ci-budget.md and "
                "infra/ci-vps/nexus-ci-host-doctor.sh"
            ),
        )
    health = summarize_health(ci_facts)
    statuses = {item.name: item.status for item in health.checks}
    messages = {item.name: item.message for item in health.checks}
    if statuses.get("runner") == "FAIL" and all(
        item.status != "FAIL" or item.name == "runner" for item in health.checks
    ):
        return DoctorCheck(
            "ci-profile",
            "ACTIVATION_REQUIRED",
            message=messages.get("runner") or "runner unavailable",
            repair=(
                "install/register the self-hosted runner on the CI VPS "
                "(/opt/nexus-runner). Absence of runner/token is activation, not a "
                "local release failure."
            ),
        )
    if health.gate == "FAIL":
        return DoctorCheck(
            "ci-profile",
            "FAIL",
            message=health.summary,
            repair="fix CI-host fixture facts (disk/memory/cache/tools); do not SSH",
        )
    if health.gate == "WARN":
        return DoctorCheck(
            "ci-profile",
            "WARN",
            message=health.summary,
            repair="review CI-host fixture warnings in docs/operations/ci-budget.md",
        )
    return DoctorCheck("ci-profile", "PASS", message=health.summary)


def _check_github(
    env: Mapping[str, str], github_project_ids: Mapping[str, str] | None
) -> DoctorCheck:
    ids = dict(github_project_ids) if github_project_ids is not None else {}
    if github_project_ids is None:
        for key in (
            "NEXUS_GITHUB_PROJECT_ID",
            "NEXUS_GITHUB_PROJECT_ITEM_ID",
        ):
            value = str(env.get(key) or "").strip()
            if value:
                ids[key] = value
    if ids:
        return DoctorCheck(
            "github",
            "PASS",
            message="GitHub Project node IDs present in user configuration",
        )
    return DoctorCheck(
        "github",
        "ACTIVATION_REQUIRED",
        message=(
            "GitHub Project live IDs are absent (core/project/project-fields.toml "
            "stores field names; IDs stay in user configuration)"
        ),
        repair=(
            "set NEXUS_GITHUB_PROJECT_ID in the user environment "
            "(id_stored_in_user_configuration = true). Do not commit project node IDs "
            "or tokens. `gh` is optional until Plan 8 GitHub activation."
        ),
    )


def _check_posthog(root: Path, profile: str, env: Mapping[str, str]) -> DoctorCheck:
    config_path = root / "core" / "observability" / "posthog.toml"
    config = load_posthog_config(config_path, environ=env)
    snapshot = observability_doctor_report(config)
    repair = (
        "set enabled = true in core/observability/posthog.toml and export "
        "POSTHOG_PERSONAL_API_KEY (never commit the key; never log it)"
    )
    if config.enabled and config.host and config.project_id:
        return DoctorCheck(
            "posthog",
            "PASS",
            message="PostHog config present (secrets redacted via safe_dict)",
        )
    if profile == "local":
        return DoctorCheck(
            "posthog",
            "SKIP",
            required=False,
            message=(
                "PostHog is disabled/unconfigured; optional for local harness usability "
                f"({config_path})"
            ),
        )
    if profile == "ci-host":
        return DoctorCheck(
            "posthog",
            "SKIP",
            required=False,
            message="PostHog is not required for hermetic CI-host doctor",
        )
    return DoctorCheck(
        "posthog",
        "ACTIVATION_REQUIRED",
        message=(
            f"PostHog is disabled/unconfigured in {config_path} "
            f"(status={snapshot.get('status')})"
        ),
        repair=repair,
    )


def _check_release(root: Path) -> DoctorCheck:
    manifest = root / "release" / "MANIFEST.json"
    archive = root / "release" / "nexus-harness-v4.tar.gz"
    if manifest.is_file() or archive.is_file():
        return DoctorCheck("release", "PASS", message="release artifacts present")
    return DoctorCheck(
        "release",
        "ACTIVATION_REQUIRED",
        message="release archive/manifest is not assembled yet",
        repair="run the release builder (scripts/nexus / Task 5) when assembling v4",
    )
