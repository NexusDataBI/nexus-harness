from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from nexus_harness.config import load_toml
from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryRecord,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.store import read_memory, write_memory

_REPO_ROOT = Path(__file__).resolve().parents[3]
_POLICY_PATH = _REPO_ROOT / "core" / "memory" / "memory-policy.toml"

_SIGNAL_TO_TYPE = {
    "architecture_decision": MemoryType.DECISION,
    "invariant": MemoryType.INVARIANT,
    "component_fact": MemoryType.COMPONENT,
    "reusable_pattern": MemoryType.PATTERN,
    "confirmed_bug_lesson": MemoryType.LESSON,
    "confirmed_incident": MemoryType.INCIDENT,
}

_TYPE_SOURCE_KEYS = {
    MemoryType.DECISION: "decision_sources",
    MemoryType.INVARIANT: "invariant_sources",
    MemoryType.COMPONENT: "component_sources",
    MemoryType.LESSON: "lesson_sources",
    MemoryType.INCIDENT: "incident_sources",
}

_DETERMINISTIC_KINDS = frozenset({"deterministic_evidence", "deterministic-evidence"})
_PATTERN_AUTHORITY = frozenset({"approved_spec", "adr"})
_PROMOTABLE = frozenset({MemoryStatus.CANDIDATE, MemoryStatus.STALE})


class MemoryPromotionError(ValueError):
    """Raised when a memory cannot be promoted under policy."""


@dataclass(frozen=True)
class CandidateSignal:
    kind: str
    title: str
    statement: str
    sources: tuple[MemorySource, ...]
    evidence_ids: tuple[str, ...] = ()
    related_paths: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _promotion_policy() -> dict:
    return load_toml(_POLICY_PATH).get("promotion", {})


def _evidence_fields(result: object) -> tuple[object, object, object]:
    if isinstance(result, dict):
        return result.get("exit_code"), result.get("diff"), result.get("current_diff")
    return (
        getattr(result, "exit_code", None),
        getattr(result, "diff", None),
        getattr(result, "current_diff", None),
    )


def _validate_deterministic_evidence(
    record: MemoryRecord,
    *,
    evidence_lookup,
    current_diff: str | None,
) -> None:
    for source in record.sources:
        if source.kind not in _DETERMINISTIC_KINDS:
            continue
        if not source.ref:
            raise MemoryPromotionError("deterministic evidence id missing")
        if record.evidence_ids and source.ref not in record.evidence_ids:
            raise MemoryPromotionError("deterministic evidence id missing")
        if evidence_lookup is None:
            continue
        try:
            result = evidence_lookup(source.ref)
        except Exception as exc:
            raise MemoryPromotionError("deterministic evidence lookup failed") from exc
        if result is None:
            raise MemoryPromotionError("deterministic evidence lookup failed")
        exit_code, stored_diff, result_current = _evidence_fields(result)
        if exit_code != 0:
            raise MemoryPromotionError("deterministic evidence exit code")
        expected_diff = current_diff if current_diff is not None else result_current
        if expected_diff is not None and stored_diff != expected_diff:
            raise MemoryPromotionError("deterministic evidence diff mismatch")


def _validate_sources(record: MemoryRecord, policy: dict) -> None:
    if record.type == MemoryType.PATTERN:
        if any(source.kind in _PATTERN_AUTHORITY for source in record.sources):
            return
        min_refs = int(policy.get("pattern_min_independent_sources", 2))
        distinct_refs = {source.ref for source in record.sources if source.ref}
        if len(distinct_refs) < min_refs:
            raise MemoryPromotionError("pattern requires independent sources")
        return

    allowed_key = _TYPE_SOURCE_KEYS.get(record.type)
    if allowed_key is None:
        raise MemoryPromotionError("unsupported memory type")
    allowed = set(policy.get(allowed_key, ()))
    if not any(source.kind in allowed for source in record.sources):
        raise MemoryPromotionError("missing authoritative source")


def verify_record(
    record: MemoryRecord,
    current_commit: str,
    evidence_lookup=None,
    current_diff: str | None = None,
) -> MemoryRecord:
    if record.status not in _PROMOTABLE:
        raise MemoryPromotionError("record is not eligible for verification")
    policy = _promotion_policy()
    _validate_sources(record, policy)
    _validate_deterministic_evidence(
        record,
        evidence_lookup=evidence_lookup,
        current_diff=current_diff,
    )
    return replace(
        record,
        status=MemoryStatus.VERIFIED,
        confidence=MemoryConfidence.HIGH,
        verified_at=_utc_now(),
        valid_at_commit=current_commit,
    )


def collect_memory_candidates(
    *,
    project_id: str,
    task_id: str,
    signals: tuple[CandidateSignal, ...],
) -> list[MemoryDraft]:
    del task_id
    drafts = []
    for signal in signals:
        memory_type = _SIGNAL_TO_TYPE.get(signal.kind)
        if memory_type is None:
            continue
        drafts.append(
            MemoryDraft(
                type=memory_type,
                scope=MemoryScope.PROJECT,
                project_id=project_id,
                title=signal.title,
                body=signal.statement,
                sources=signal.sources,
                evidence_ids=signal.evidence_ids,
                related_paths=signal.related_paths,
                tags=signal.tags,
            )
        )
    return drafts


def supersede_record(old: MemoryRecord, new_id: str) -> MemoryRecord:
    if old.id == new_id:
        raise MemoryPromotionError("cannot supersede a memory with itself")
    return replace(old, status=MemoryStatus.SUPERSEDED)


def verify_memory(
    project_root,
    memory_id,
    *,
    current_commit,
    evidence_lookup=None,
    current_diff=None,
):
    record = read_memory(Path(project_root), memory_id)
    verified = verify_record(
        record,
        current_commit=current_commit,
        evidence_lookup=evidence_lookup,
        current_diff=current_diff,
    )
    return write_memory(Path(project_root), verified, replace=True)


def supersede_memory(project_root, old_memory_id, replacement_memory_id):
    old = read_memory(Path(project_root), old_memory_id)
    updated = supersede_record(old, replacement_memory_id)
    return write_memory(Path(project_root), updated, replace=True)


def promote_to_portfolio_draft(records, title, body, tags) -> MemoryDraft:
    verified_project = [
        record
        for record in records
        if record.status == MemoryStatus.VERIFIED
        and record.scope == MemoryScope.PROJECT
    ]
    if not verified_project:
        raise MemoryPromotionError("portfolio requires a verified project source")
    return MemoryDraft(
        type=verified_project[0].type,
        scope=MemoryScope.PORTFOLIO,
        project_id=None,
        title=title,
        body=body,
        sources=tuple(MemorySource("project_memory", record.id) for record in records),
        tags=tuple(tags),
    )
