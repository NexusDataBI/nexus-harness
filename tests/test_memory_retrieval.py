import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.retrieval import (
    MemoryQueryContext,
    default_index_path,
    rebuild_index,
    search_memory,
)
from nexus_harness.memory.store import (
    init_project_memory,
    load_project_memories,
    write_memory,
)


def _verified(record):
    return replace(
        record, status=MemoryStatus.VERIFIED, confidence=MemoryConfidence.HIGH
    )


class MemoryRetrievalTests(unittest.TestCase):
    def test_matching_path_and_tag_rank_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_home = root / "cache"
            init_project_memory(root)
            first = MemoryDraft(
                type=MemoryType.INVARIANT,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Auth token rotation",
                body="Rotate auth credentials without invalidating active migration jobs.",
                related_paths=("src/auth/**",),
                tags=("auth",),
            ).to_record()
            second = MemoryDraft(
                type=MemoryType.LESSON,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="CSS layout lesson",
                body="Prefer grid for this dashboard.",
                tags=("frontend",),
            ).to_record()
            first = _verified(first)
            second = _verified(second)
            write_memory(root, first)
            write_memory(root, second)
            hits = search_memory(
                root,
                "auth rotation",
                MemoryQueryContext(
                    project_id="repo-1",
                    affected_paths=("src/auth/session.py",),
                    tags=("auth",),
                ),
                cache_home=cache_home,
            )
            self.assertEqual(hits[0].record.id, first.id)

    @patch("nexus_harness.memory.retrieval.fts5_available", return_value=False)
    def test_lexical_fallback_works_without_fts5(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_home = root / "cache"
            init_project_memory(root)
            record = MemoryDraft(
                type=MemoryType.LESSON,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Retry idempotency",
                body="Webhook retries require stable idempotency keys.",
                tags=("webhook", "idempotency"),
            ).to_record()
            record = _verified(record)
            write_memory(root, record)
            hits = search_memory(
                root,
                "webhook idempotency",
                MemoryQueryContext(project_id="repo-1"),
                cache_home=cache_home,
            )
            self.assertGreaterEqual(len(hits), 1)
            self.assertEqual(hits[0].record.id, record.id)

    def test_search_survives_deleted_memory_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_home = root / "cache"
            init_project_memory(root)
            record = MemoryDraft(
                type=MemoryType.LESSON,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Retry idempotency",
                body="Webhook retries require stable idempotency keys.",
                tags=("webhook", "idempotency"),
            ).to_record()
            record = _verified(record)
            write_memory(root, record)
            db_path = default_index_path("repo-1", cache_home=cache_home)
            rebuild_index(load_project_memories(root), db_path)
            self.assertTrue(db_path.is_file())
            first_hits = search_memory(
                root,
                "webhook idempotency",
                MemoryQueryContext(project_id="repo-1"),
                cache_home=cache_home,
            )
            self.assertGreaterEqual(len(first_hits), 1)
            top_id = first_hits[0].record.id
            db_path.unlink()
            self.assertFalse(db_path.exists())
            second_hits = search_memory(
                root,
                "webhook idempotency",
                MemoryQueryContext(project_id="repo-1"),
                cache_home=cache_home,
            )
            self.assertGreaterEqual(len(second_hits), 1)
            self.assertEqual(second_hits[0].record.id, top_id)
            self.assertEqual(top_id, record.id)
