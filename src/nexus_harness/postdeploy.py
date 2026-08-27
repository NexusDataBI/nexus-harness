"""Post-deploy runtime verification.

Health/smoke are deploy mechanics (Plan 4). This module only evaluates
runtime confidence and signals rollback/incident workflow — it does not
SSH, docker compose, or kubectl.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

GATE_PASS = "PASS"
GATE_FAIL = "FAIL"
GATE_INSUFFICIENT = "INSUFFICIENT_DATA"

_DEFAULT_MINIMUM_SAMPLE = 5


@dataclass(frozen=True)
class PostDeployResult:
    gate: str
    reason: str
    rollback_handoff: str | None = None
    issue_close_eligible: bool = False
    window_start: datetime | None = None
    window_end: datetime | None = None
    minimum_sample: int = _DEFAULT_MINIMUM_SAMPLE
    observations_available: int | None = None


def evaluate_postdeploy(
    health: Any = True,
    smoke: Any = True,
    new_error_regression: bool = False,
    *,
    observations_available: int | None = None,
    minimum_sample: int = _DEFAULT_MINIMUM_SAMPLE,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    runtime_status: str | None = None,
) -> PostDeployResult:
    """Evaluate post-deploy runtime confidence.

    Observation windows are declarative. Callers/schedulers decide when to
    re-evaluate. This function never sleeps.
    """
    sample = int(minimum_sample or _DEFAULT_MINIMUM_SAMPLE)
    if not _is_pass(health):
        return PostDeployResult(
            gate=GATE_FAIL,
            reason="health FAIL",
            rollback_handoff="signal",
            window_start=window_start,
            window_end=window_end,
            minimum_sample=sample,
            observations_available=observations_available,
        )
    if not _is_pass(smoke):
        return PostDeployResult(
            gate=GATE_FAIL,
            reason="smoke FAIL",
            rollback_handoff="signal",
            window_start=window_start,
            window_end=window_end,
            minimum_sample=sample,
            observations_available=observations_available,
        )
    if new_error_regression:
        return PostDeployResult(
            gate=GATE_FAIL,
            reason="confirmed high-severity release regression",
            rollback_handoff="signal",
            window_start=window_start,
            window_end=window_end,
            minimum_sample=sample,
            observations_available=observations_available,
        )

    status = str(runtime_status or "").strip().upper()
    if status in {"UNKNOWN", "UNAVAILABLE"}:
        return PostDeployResult(
            gate=GATE_INSUFFICIENT,
            reason="runtime telemetry unavailable",
            rollback_handoff=None,
            issue_close_eligible=False,
            window_start=window_start,
            window_end=window_end,
            minimum_sample=sample,
            observations_available=observations_available,
        )

    observed = observations_available
    if observed is None or int(observed) < sample:
        return PostDeployResult(
            gate=GATE_INSUFFICIENT,
            reason="telemetry observation insufficient",
            rollback_handoff=None,
            issue_close_eligible=False,
            window_start=window_start,
            window_end=window_end,
            minimum_sample=sample,
            observations_available=observed,
        )

    return PostDeployResult(
        gate=GATE_PASS,
        reason="health, smoke, and sufficient runtime evidence",
        rollback_handoff=None,
        issue_close_eligible=True,
        window_start=window_start,
        window_end=window_end,
        minimum_sample=sample,
        observations_available=observed,
    )


def _is_pass(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().upper()
    return text in {"PASS", "OK", "TRUE", "1"}
