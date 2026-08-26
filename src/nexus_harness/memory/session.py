from __future__ import annotations

import json
from pathlib import Path

from nexus_harness.memory.capsule import build_context_capsule, load_capsule_policy
from nexus_harness.memory.lifecycle import MemoryPromotionError, verify_record
from nexus_harness.memory.models import MemoryDraft
from nexus_harness.memory.retrieval import MemoryQueryContext, search_memory
from nexus_harness.memory.store import atomic_write_json, write_memory


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
    hits = search_memory(
        Path(project_root),
        query,
        context,
        portfolio_root=portfolio_root,
        cache_home=cache_home,
    )
    return build_context_capsule(
        project_id=project_id,
        diff_hash=None,
        hits=hits,
        hot_memory_ids=(),
        policy=load_capsule_policy(),
    )


def checkpoint_memory_candidates(path, candidates):
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
