from __future__ import annotations

import json
from pathlib import Path

from nexus_harness.memory.capsule import build_context_capsule, load_capsule_policy
from nexus_harness.memory.freshness import FreshnessStatus
from nexus_harness.memory.guard import validate_memory_record
from nexus_harness.memory.lifecycle import MemoryPromotionError, verify_record
from nexus_harness.memory.models import (
    MemoryDraft,
    MemorySensitivity,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.retrieval import MemoryHit, MemoryQueryContext, search_memory
from nexus_harness.memory.store import MemoryStoreError, atomic_write_json, write_memory

_HOT_PREFERRED = (MemoryType.INVARIANT, MemoryType.DECISION)
_HOT_ITEM_CAP = 4


def _hot_memory_ids(hits: list[MemoryHit], max_items: int) -> tuple[str, ...]:
    eligible = [
        hit
        for hit in hits
        if hit.record.status == MemoryStatus.VERIFIED
        and hit.record.sensitivity != MemorySensitivity.CONFIDENTIAL
        and hit.freshness != FreshnessStatus.STALE
        and hit.record.status != MemoryStatus.STALE
    ]
    preferred = [hit for hit in eligible if hit.record.type in _HOT_PREFERRED]
    others = [hit for hit in eligible if hit.record.type not in _HOT_PREFERRED]
    cap = min(_HOT_ITEM_CAP, max_items)
    return tuple(hit.record.id for hit in (*preferred, *others)[:cap])


def session_recall(
    project_root,
    *,
    project_id,
    query,
    affected_paths=(),
    portfolio_root=None,
    cache_home=None,
):
    context = MemoryQueryContext(
        project_id=project_id,
        affected_paths=tuple(affected_paths),
        include_stale=True,
    )
    policy = load_capsule_policy()
    findings: list[dict[str, str]] = []
    try:
        hits = search_memory(
            Path(project_root),
            query,
            context,
            portfolio_root=portfolio_root,
            cache_home=cache_home,
            findings=findings,
        )
    except (MemoryStoreError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        findings.append(
            {
                "code": "memory_record_excluded",
                "path": str(project_root),
                "message": "record was excluded because its sidecar is invalid",
            }
        )
        return build_context_capsule(
            project_id=project_id,
            diff_hash=None,
            hits=(),
            hot_memory_ids=(),
            policy=policy,
            findings=findings,
        )
    return build_context_capsule(
        project_id=project_id,
        diff_hash=None,
        hits=hits,
        hot_memory_ids=_hot_memory_ids(hits, policy.max_items),
        policy=policy,
        findings=findings,
    )


def checkpoint_memory_candidates(path, candidates):
    for item in candidates:
        validate_memory_record(item.to_record())
    payload = [item.to_json_dict() for item in candidates]
    atomic_write_json(Path(path), payload)
    return Path(path)


def restore_memory_candidates(path):
    target = Path(path)
    if not target.exists():
        return []
    return [
        MemoryDraft.from_json_dict(item)
        for item in json.loads(target.read_text(encoding="utf-8"))
    ]


def consolidate_memory(
    project_root, candidates, *, current_commit, evidence_lookup=None
):
    results = []
    for draft in candidates:
        record = draft.to_record()
        try:
            record = verify_record(
                record,
                current_commit=current_commit,
                evidence_lookup=evidence_lookup,
            )
        except MemoryPromotionError:
            record = record
        results.append(write_memory(Path(project_root), record))
    return results
