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
    tolerance: float = 0.0


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


def evaluate_metric(metric: Metric) -> MetricResult:
    if metric.mode == "absolute":
        floor = 0 if metric.threshold is None else metric.threshold
        passed = _passes(metric.current, floor, metric.direction)
    elif metric.mode == "ratchet":
        passed = metric.baseline is None or _passes(
            metric.current, metric.baseline, metric.direction
        )
    elif metric.mode == "budget":
        passed = metric.baseline is None or _passes(
            metric.current, metric.baseline, metric.direction, metric.tolerance
        )
    else:
        raise ValueError(f"unknown mode: {metric.mode}")
    return MetricResult(
        name=metric.name,
        status="PASS" if passed else "FAIL",
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
) -> QualityReport:
    results = [evaluate_metric(metric) for metric in metrics]
    required_failed = any(item.required and item.status == "FAIL" for item in results)
    return QualityReport(
        gate="FAIL" if required_failed else "PASS",
        metrics=results,
        profile=profile,
        diff_hash=diff_hash,
        score=score,
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


def _entry_direction(name: str, entry, directions: dict) -> str:
    if isinstance(entry, dict) and entry.get("direction"):
        return entry["direction"]
    return directions.get(name, _DEFAULT_DIRECTIONS.get(name, "higher"))


def validate_baseline_change(base, proposed, measured, policy=None) -> None:
    policy = policy or load_ratchet_policy()
    directions = {**_DEFAULT_DIRECTIONS, **policy.get("directions", {})}
    precision = float(policy.get("precision", {}).get("default", _DEFAULT_PRECISION))
    promote = bool(policy.get("promote_improvements", True))
    names = set(base) | set(proposed) | set(measured)
    for name in sorted(names):
        base_entry = base.get(name)
        proposed_entry = proposed.get(name, base_entry)
        measured_entry = measured.get(name)
        direction = _entry_direction(
            name,
            proposed_entry if proposed_entry is not None else base_entry,
            directions,
        )
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
