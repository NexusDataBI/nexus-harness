from dataclasses import asdict, dataclass, field
from pathlib import Path

from nexus_harness.config import load_toml

_CORE_QUALITY = Path(__file__).resolve().parents[2] / "core" / "quality"
_DEFAULT_DIRECTIONS = {
    "coverage": "higher",
    "lint_warnings": "lower",
    "duplication": "lower",
    "build_type_errors": "lower",
    "failing_tests": "lower",
    "critical_security": "lower",
    "performance": "lower",
}
_DEFAULT_PRECISION = 0.01


@dataclass
class Metric:
    name: str
    current: float | int | bool
    baseline: float | int | bool | None = None
    mode: str = "ratchet"
    direction: str = "higher"
    required: bool = True
    threshold: float | int | bool | None = None
    tolerance: float | None = None


@dataclass
class MetricResult:
    name: str
    status: str
    current: float | int | bool
    baseline: float | int | bool | None = None
    mode: str = "ratchet"
    direction: str = "higher"
    required: bool = True


@dataclass
class QualityReport:
    gate: str
    metrics: list[MetricResult] = field(default_factory=list)
    profile: str | None = None
    diff_hash: str | None = None
    score: float | None = None
    change_head_sha: str | None = None
    checkout_sha: str | None = None

    def to_dict(self) -> dict:
        payload = {
            "gate": self.gate,
            "metrics": [asdict(item) for item in self.metrics],
        }
        if self.profile is not None:
            payload["profile"] = self.profile
        if self.diff_hash is not None:
            payload["diff_hash"] = self.diff_hash
        if self.score is not None:
            payload["score"] = self.score
        if self.change_head_sha is not None:
            payload["change_head_sha"] = self.change_head_sha
        if self.checkout_sha is not None:
            payload["checkout_sha"] = self.checkout_sha
        return payload


def _higher_is_better(direction: str) -> bool:
    if direction == "higher":
        return True
    if direction == "lower":
        return False
    raise ValueError(f"unknown direction: {direction}")


def _as_number(value):
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return value


def _passes(current, floor, direction: str, tolerance: float = 0.0) -> bool:
    current_n = _as_number(current)
    floor_n = _as_number(floor)
    if _higher_is_better(direction):
        return current_n >= floor_n - tolerance
    return current_n <= floor_n + tolerance


def _improved(current, floor, direction: str, precision: float) -> bool:
    current_n = _as_number(current)
    floor_n = _as_number(floor)
    if _higher_is_better(direction):
        return current_n > floor_n + precision
    return current_n < floor_n - precision


def _weakened(proposed, base, direction: str, precision: float) -> bool:
    proposed_n = _as_number(proposed)
    base_n = _as_number(base)
    if _higher_is_better(direction):
        return proposed_n < base_n - precision
    return proposed_n > base_n + precision


def evaluate_metric(metric: Metric, policy: dict | None = None) -> MetricResult:
    policy = policy if policy is not None else load_ratchet_policy()
    if metric.mode == "absolute":
        floor = 0 if metric.threshold is None else metric.threshold
        passed = _passes(metric.current, floor, metric.direction)
        status = "PASS" if passed else "FAIL"
    elif metric.mode in {"ratchet", "budget"}:
        if metric.baseline is None:
            status = "BOOTSTRAP_REQUIRED" if metric.required else "NOT_APPLICABLE"
        else:
            tolerance = 0.0
            if metric.mode == "budget":
                if metric.tolerance is not None:
                    tolerance = metric.tolerance
                else:
                    tolerance = float(
                        policy.get("budget", {}).get("default_tolerance", 0.0)
                    )
            passed = _passes(
                metric.current, metric.baseline, metric.direction, tolerance
            )
            status = "PASS" if passed else "FAIL"
    else:
        raise ValueError(f"unknown mode: {metric.mode}")
    return MetricResult(
        name=metric.name,
        status=status,
        current=metric.current,
        baseline=metric.baseline,
        mode=metric.mode,
        direction=metric.direction,
        required=metric.required,
    )


def evaluate_report(
    metrics,
    *,
    score: float | None = None,
    profile: str | None = None,
    diff_hash: str | None = None,
    change_head_sha: str | None = None,
    checkout_sha: str | None = None,
) -> QualityReport:
    results = [evaluate_metric(metric) for metric in metrics]
    required_failed = any(item.required and item.status == "FAIL" for item in results)
    required_bootstrap = any(
        item.required and item.status == "BOOTSTRAP_REQUIRED" for item in results
    )
    if required_failed:
        gate = "FAIL"
    elif required_bootstrap:
        gate = "BOOTSTRAP_REQUIRED"
    else:
        gate = "PASS"
    return QualityReport(
        gate=gate,
        metrics=results,
        profile=profile,
        diff_hash=diff_hash,
        score=score,
        change_head_sha=change_head_sha,
        checkout_sha=checkout_sha,
    )


def load_ratchet_policy(path: Path | None = None) -> dict:
    return load_toml(path or _CORE_QUALITY / "ratchet.toml")


def load_quality_profile(name: str, path: Path | None = None) -> dict:
    profiles = load_toml(path or _CORE_QUALITY / "profiles.toml")["profiles"]
    if name not in profiles:
        raise ValueError(f"unknown quality profile: {name}")
    return profiles[name]


def _entry_value(entry):
    if isinstance(entry, dict):
        return entry["value"]
    return entry


def _entry_direction(name: str, base_entry, policy_directions: dict) -> str:
    if name in policy_directions:
        return policy_directions[name]
    if isinstance(base_entry, dict) and base_entry.get("direction"):
        return base_entry["direction"]
    return _DEFAULT_DIRECTIONS.get(name, "higher")


def validate_baseline_change(base, proposed, measured, policy=None) -> None:
    policy = policy or load_ratchet_policy()
    policy_directions = policy.get("directions", {})
    precision = float(policy.get("precision", {}).get("default", _DEFAULT_PRECISION))
    promote = bool(policy.get("promote_improvements", True))
    names = set(base) | set(proposed) | set(measured)
    for name in sorted(names):
        base_entry = base.get(name)
        proposed_entry = proposed.get(name, base_entry)
        measured_entry = measured.get(name)
        direction = _entry_direction(
            name,
            base_entry,
            policy_directions,
        )
        if (
            isinstance(proposed_entry, dict)
            and proposed_entry.get("direction") is not None
            and proposed_entry["direction"] != direction
        ):
            raise ValueError(f"cannot change {name} baseline direction")
        if base_entry is not None and proposed_entry is not None:
            base_value = _entry_value(base_entry)
            proposed_value = _entry_value(proposed_entry)
            if _weakened(proposed_value, base_value, direction, precision):
                raise ValueError(f"cannot weaken {name} baseline")
        if (
            promote
            and base_entry is not None
            and measured_entry is not None
            and proposed_entry is not None
        ):
            base_value = _entry_value(base_entry)
            proposed_value = _entry_value(proposed_entry)
            measured_value = _entry_value(measured_entry)
            if _improved(measured_value, base_value, direction, precision):
                if (
                    abs(_as_number(proposed_value) - _as_number(measured_value))
                    > precision
                ):
                    raise ValueError(
                        f"stale baseline: {name} must be promoted to measured improvement"
                    )
