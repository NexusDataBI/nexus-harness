"""Synchronize harness lifecycle to the central GitHub Project.

Status follows the user event mapping. Quality/Security come from gate
reports. Project/item/field node IDs are caller/user configuration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from nexus_harness.config import load_toml

_CORE_FIELDS = (
    Path(__file__).resolve().parents[2] / "core" / "project" / "project-fields.toml"
)
_FIELD_ORDER = ("Status", "Quality", "Security")
_GATE_FAILURES = frozenset({"BLOCKED", "FAIL"})


@dataclass(frozen=True)
class ProjectSyncResult:
    status: str
    updated: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()


def load_project_fields(path: Path | None = None) -> dict:
    return load_toml(path or _CORE_FIELDS)


def lifecycle_to_project_status(stage, gate_status, *, event=None) -> str:
    fields = load_project_fields()
    events = fields.get("status_from_event") or {}
    stages = fields.get("status_from_lifecycle") or {}
    status = str(gate_status or "").strip().upper()
    event_key = str(event).strip() if event else ""

    if status in _GATE_FAILURES or event_key == "gate_failure":
        return str(events.get("gate_failure") or stages.get("blocked") or "Blocked")
    if event_key:
        if event_key not in events:
            raise ValueError(f"unknown lifecycle event: {event_key}")
        return str(events[event_key])
    stage_number = _as_stage(stage)
    if stage_number == 1 and status == "PASS":
        return str(events.get("acceptance_ready") or "Ready")
    mapped = _stage_status(stages, stage_number)
    if mapped is None:
        raise ValueError(f"unknown lifecycle stage: {stage}")
    return mapped


def project_field_values(
    *,
    stage,
    gate_status,
    event: str | None = None,
    quality_report=None,
    security_report=None,
) -> dict[str, str]:
    quality = _report_gate(quality_report)
    security = _report_gate(security_report)
    status_input = gate_status
    event_input = event
    if quality == "FAIL" or security == "FAIL":
        status_input = "FAIL"
        event_input = "gate_failure"
    values = {
        "Status": lifecycle_to_project_status(stage, status_input, event=event_input)
    }
    if quality is not None:
        values["Quality"] = quality
    if security is not None:
        values["Security"] = security
    return values


def sync_project_item(
    github: object,
    *,
    project_id: str,
    item_id: str,
    field_ids: Mapping[str, str],
    current_fields: Mapping[str, object] | None = None,
    stage,
    gate_status,
    event: str | None = None,
    quality_report=None,
    security_report=None,
    authorize_remote_mutation: bool = False,
) -> ProjectSyncResult:
    desired = project_field_values(
        stage=stage,
        gate_status=gate_status,
        event=event,
        quality_report=quality_report,
        security_report=security_report,
    )
    current = dict(current_fields or {})
    changed = _ordered(
        name for name, value in desired.items() if current.get(name) != value
    )
    if not authorize_remote_mutation:
        return ProjectSyncResult(
            status=desired["Status"],
            updated=(),
            changed=changed,
        )

    ids = dict(field_ids)
    for name in changed:
        field_id = ids.get(name)
        if not field_id:
            raise ValueError(f"missing field id for {name}")
        github.project_item_update(
            item_id,
            project_id,
            field_id,
            text=str(desired[name]),
        )
    return ProjectSyncResult(
        status=desired["Status"],
        updated=changed,
        changed=changed,
    )


def _as_stage(stage) -> int:
    try:
        return int(stage)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unknown lifecycle stage: {stage}") from exc


def _stage_status(stages: Mapping[object, object], stage: int) -> str | None:
    for key in (stage, str(stage)):
        if key in stages:
            return str(stages[key])
    return None


def _report_gate(report) -> str | None:
    if report is None or isinstance(report, str):
        return None
    if isinstance(report, Mapping):
        gate = report.get("gate")
    else:
        gate = getattr(report, "gate", None)
    if gate is None or str(gate).strip() == "":
        return None
    return str(gate)


def _ordered(names) -> tuple[str, ...]:
    rank = {name: index for index, name in enumerate(_FIELD_ORDER)}
    return tuple(sorted(names, key=lambda name: (rank.get(name, len(rank)), name)))
