"""CI-host health summary and graph-estimated CI budget report.

No external monitoring SaaS (Datadog/Grafana/Sentry). Facts are injectable so
unit tests and the shell doctor can feed the same summary without hitting a VPS.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from nexus_harness.config import load_toml

_CORE_GRAPH = Path(__file__).resolve().parents[2] / "core" / "graph"
_SCHEDULER_POLICY = _CORE_GRAPH / "scheduler.toml"

DISK_FAIL_PERCENT = 95.0
DISK_WARN_PERCENT = 85.0
MEMORY_FAIL_PERCENT = 95.0
MEMORY_WARN_PERCENT = 85.0
CLOCK_SKEW_FAIL_SECONDS = 120.0
CLOCK_SKEW_WARN_SECONDS = 30.0

DEFAULT_TARGET_GITHUB_HOSTED_MINUTES = 0.0


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: str  # PASS | WARN | FAIL
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HealthReport:
    gate: str  # PASS | WARN | FAIL
    checks: tuple[HealthCheck, ...] = ()
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "gate": self.gate,
            "summary": self.summary,
            "checks": [item.to_dict() for item in self.checks],
        }


@dataclass(frozen=True)
class CiBudgetReport:
    self_hosted_cpu_minutes: float
    github_hosted_minutes: float
    target_github_hosted_minutes: float = DEFAULT_TARGET_GITHUB_HOSTED_MINUTES
    within_policy: bool = True
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


def load_ci_budget_policy(path: Path | None = None) -> dict:
    """Load scheduler billing targets (default: core/graph/scheduler.toml)."""
    return load_toml(path or _SCHEDULER_POLICY)


def target_github_hosted_minutes(policy: Mapping[str, Any] | None = None) -> float:
    policy = policy or load_ci_budget_policy()
    billing = (
        policy.get("billing") if isinstance(policy.get("billing"), Mapping) else {}
    )
    raw = billing.get(
        "target_github_hosted_minutes_per_normal_pr",
        DEFAULT_TARGET_GITHUB_HOSTED_MINUTES,
    )
    return float(raw)


def summarize_health(facts: Mapping[str, Any]) -> HealthReport:
    """Summarize CI-host posture from an injectable facts dict.

    Recognized keys (all optional except what the caller cares to assert):
    - disk_percent (float)
    - memory_percent (float)
    - runner (bool)
    - docker / container_engine (bool)
    - cache_writable (bool)
    - clock_skew_seconds (float absolute skew)
    - required_directories (mapping name→bool present, or sequence of missing names)
    - tools (mapping tool→bool available)
    """
    checks: list[HealthCheck] = []

    if "disk_percent" in facts:
        checks.append(
            _check_percent(
                "disk",
                float(facts["disk_percent"]),
                DISK_FAIL_PERCENT,
                DISK_WARN_PERCENT,
            )
        )

    if "memory_percent" in facts:
        checks.append(
            _check_percent(
                "memory",
                float(facts["memory_percent"]),
                MEMORY_FAIL_PERCENT,
                MEMORY_WARN_PERCENT,
            )
        )

    if "runner" in facts:
        checks.append(
            HealthCheck(
                name="runner",
                status="PASS" if bool(facts["runner"]) else "FAIL",
                message="runner healthy" if facts["runner"] else "runner unavailable",
            )
        )

    engine = facts.get("docker", facts.get("container_engine"))
    if engine is not None:
        checks.append(
            HealthCheck(
                name="container_engine",
                status="PASS" if bool(engine) else "FAIL",
                message="container engine healthy"
                if engine
                else "container engine unavailable",
            )
        )

    if "cache_writable" in facts:
        writable = bool(facts["cache_writable"])
        checks.append(
            HealthCheck(
                name="cache_writable",
                status="PASS" if writable else "FAIL",
                message="cache directory writable"
                if writable
                else "cache directory not writable",
            )
        )

    if "clock_skew_seconds" in facts:
        checks.append(_check_clock(float(facts["clock_skew_seconds"])))

    if "required_directories" in facts:
        checks.extend(_check_required_directories(facts["required_directories"]))

    if "tools" in facts:
        checks.extend(_check_tools(facts["tools"]))

    gate = _aggregate_gate(checks)
    summary = _format_summary(gate, checks)
    return HealthReport(gate=gate, checks=tuple(checks), summary=summary)


def estimate_ci_budget(
    nodes: Sequence[Any] | None = None,
    *,
    self_hosted_cpu_minutes: float | None = None,
    github_hosted_minutes: float | None = None,
    policy: Mapping[str, Any] | None = None,
    history: Mapping[str, Any] | None = None,
) -> CiBudgetReport:
    """Report graph-estimated self-hosted CPU minutes and GitHub-hosted minutes.

    Prefer explicit minute overrides; otherwise sum ``estimated_cost`` on nodes by
    ``execution_target``. History may supply observed minutes when graph nodes are
    absent. Policy default target is ``github_hosted_minutes = 0`` for ordinary
    private-repository PRs.
    """
    target = target_github_hosted_minutes(policy)
    notes: list[str] = []

    sh = self_hosted_cpu_minutes
    gh = github_hosted_minutes

    if nodes is not None and (sh is None or gh is None):
        summed_sh, summed_gh = _sum_graph_minutes(nodes)
        if sh is None:
            sh = summed_sh
        if gh is None:
            gh = summed_gh
        notes.append(
            "minutes estimated from graph node estimated_cost by execution_target"
        )

    if history is not None:
        if sh is None and "self_hosted_cpu_minutes" in history:
            sh = float(history["self_hosted_cpu_minutes"])
            notes.append("self-hosted minutes taken from CI history")
        if gh is None and "github_hosted_minutes" in history:
            gh = float(history["github_hosted_minutes"])
            notes.append("GitHub-hosted minutes taken from CI history")

    if sh is None:
        sh = 0.0
    if gh is None:
        gh = 0.0

    within = float(gh) <= float(target) + 1e-9
    if not within:
        notes.append(
            f"GitHub-hosted minutes {gh} exceed policy target {target} "
            "(ordinary private-repo PRs should be 0)"
        )
    else:
        notes.append(
            f"policy target github_hosted_minutes={target} for ordinary private-repository PRs"
        )

    return CiBudgetReport(
        self_hosted_cpu_minutes=float(sh),
        github_hosted_minutes=float(gh),
        target_github_hosted_minutes=float(target),
        within_policy=within,
        notes=tuple(notes),
    )


def format_ci_budget_report(report: CiBudgetReport) -> str:
    """Human-readable CI budget block (no SaaS)."""
    lines = [
        "CI budget report",
        f"  self_hosted_cpu_minutes: {report.self_hosted_cpu_minutes}",
        f"  github_hosted_minutes:   {report.github_hosted_minutes}",
        f"  target_github_hosted:    {report.target_github_hosted_minutes}",
        f"  within_policy:           {report.within_policy}",
    ]
    for note in report.notes:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def _check_percent(
    name: str, percent: float, fail_at: float, warn_at: float
) -> HealthCheck:
    if percent >= fail_at:
        return HealthCheck(
            name=name,
            status="FAIL",
            message=f"{name} at {percent}% (>= {fail_at}% hard fail)",
        )
    if percent >= warn_at:
        return HealthCheck(
            name=name,
            status="WARN",
            message=f"{name} at {percent}% (>= {warn_at}% warn)",
        )
    return HealthCheck(
        name=name,
        status="PASS",
        message=f"{name} at {percent}%",
    )


def _check_clock(skew_seconds: float) -> HealthCheck:
    skew = abs(float(skew_seconds))
    if skew >= CLOCK_SKEW_FAIL_SECONDS:
        return HealthCheck(
            name="clock",
            status="FAIL",
            message=f"clock skew {skew}s (>= {CLOCK_SKEW_FAIL_SECONDS}s)",
        )
    if skew >= CLOCK_SKEW_WARN_SECONDS:
        return HealthCheck(
            name="clock",
            status="WARN",
            message=f"clock skew {skew}s (>= {CLOCK_SKEW_WARN_SECONDS}s)",
        )
    return HealthCheck(
        name="clock",
        status="PASS",
        message=f"clock skew {skew}s",
    )


def _check_required_directories(value: Any) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    if isinstance(value, Mapping):
        for name, present in value.items():
            ok = bool(present)
            checks.append(
                HealthCheck(
                    name=f"dir:{name}",
                    status="PASS" if ok else "FAIL",
                    message=f"directory {name} present"
                    if ok
                    else f"required directory missing: {name}",
                )
            )
        return checks
    if isinstance(value, (list, tuple)):
        for name in value:
            checks.append(
                HealthCheck(
                    name=f"dir:{name}",
                    status="FAIL",
                    message=f"required directory missing: {name}",
                )
            )
        return checks
    raise TypeError("required_directories must be a mapping or sequence of names")


def _check_tools(value: Any) -> list[HealthCheck]:
    if not isinstance(value, Mapping):
        raise TypeError("tools must be a mapping of tool name → available bool")
    checks: list[HealthCheck] = []
    for name, available in value.items():
        ok = bool(available)
        checks.append(
            HealthCheck(
                name=f"tool:{name}",
                status="PASS" if ok else "FAIL",
                message=f"tool {name} available"
                if ok
                else f"required tool missing: {name}",
            )
        )
    return checks


def _aggregate_gate(checks: Sequence[HealthCheck]) -> str:
    if any(item.status == "FAIL" for item in checks):
        return "FAIL"
    if any(item.status == "WARN" for item in checks):
        return "WARN"
    return "PASS"


def _format_summary(gate: str, checks: Sequence[HealthCheck]) -> str:
    if not checks:
        return f"{gate}: no checks provided"
    parts = [f"{item.name}={item.status}" for item in checks]
    return f"{gate}: " + ", ".join(parts)


def _sum_graph_minutes(nodes: Iterable[Any]) -> tuple[float, float]:
    self_hosted = 0.0
    github_hosted = 0.0
    for node in nodes:
        if isinstance(node, Mapping):
            target = str(node.get("execution_target", "local"))
            cost = float(node.get("estimated_cost", 0) or 0)
        else:
            target = str(getattr(node, "execution_target", "local"))
            cost = float(getattr(node, "estimated_cost", 0) or 0)
        if target == "self_hosted":
            self_hosted += cost
        elif target == "github_hosted":
            github_hosted += cost
    return self_hosted, github_hosted
