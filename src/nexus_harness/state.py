from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import json
import os
import tempfile

from nexus_harness.failures import FailureMemory


class StageStatus(StrEnum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


@dataclass
class AcceptanceCriterion:
    id: str
    statement: str
    status: str = "FAIL"
    verification: dict = field(default_factory=dict)
    evidence: str | None = None


@dataclass
class TaskState:
    task_id: str
    repo_id: str
    stage: int = 0
    acceptance: list[AcceptanceCriterion] = field(default_factory=list)
    stage_status: dict[str, str] = field(default_factory=dict)
    issue: int | None = None
    tracking_required: bool | None = None
    current_diff_hash: str | None = None
    intent: str | None = None
    failures: FailureMemory | dict | None = None

    @classmethod
    def new(cls, task_id: str, repo_id: str) -> "TaskState":
        return cls(
            task_id=task_id,
            repo_id=repo_id,
            stage_status={str(stage): StageStatus.PENDING for stage in range(10)},
        )

    def to_dict(self) -> dict:
        payload = {
            "task_id": self.task_id,
            "repo_id": self.repo_id,
            "stage": self.stage,
            "acceptance": [
                {
                    "id": item.id,
                    "statement": item.statement,
                    "status": item.status,
                    "verification": item.verification,
                    "evidence": item.evidence,
                }
                for item in self.acceptance
            ],
            "stage_status": {
                str(key): str(value) for key, value in self.stage_status.items()
            },
        }
        if self.issue is not None:
            payload["issue"] = self.issue
        if self.tracking_required is not None:
            payload["tracking_required"] = self.tracking_required
        if self.current_diff_hash is not None:
            payload["current_diff_hash"] = self.current_diff_hash
        if self.intent is not None:
            payload["intent"] = self.intent
        if self.failures is not None:
            payload["failures"] = (
                self.failures.to_dict()
                if hasattr(self.failures, "to_dict")
                else self.failures
            )
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "TaskState":
        acceptance = [
            AcceptanceCriterion(
                id=item["id"],
                statement=item["statement"],
                status=item.get("status", "FAIL"),
                verification=item.get("verification", {}),
                evidence=item.get("evidence"),
            )
            for item in payload.get("acceptance", [])
        ]
        return cls(
            task_id=payload["task_id"],
            repo_id=payload["repo_id"],
            stage=payload.get("stage", 0),
            acceptance=acceptance,
            stage_status={
                str(key): StageStatus(value)
                for key, value in payload.get("stage_status", {}).items()
            },
            issue=payload.get("issue"),
            tracking_required=payload.get("tracking_required"),
            current_diff_hash=payload.get("current_diff_hash"),
            intent=payload.get("intent"),
            failures=_failures_from_payload(payload.get("failures")),
        )


def _failures_from_payload(raw):
    if raw is None:
        return None
    if isinstance(raw, FailureMemory):
        return raw
    return FailureMemory.from_dict(raw)


def save_task_state(state: TaskState, path: Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state.to_dict(), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, destination)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_task_state(path: Path) -> TaskState:
    with Path(path).open(encoding="utf-8") as handle:
        return TaskState.from_dict(json.load(handle))
