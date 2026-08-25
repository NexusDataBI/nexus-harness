import unittest

from nexus_harness.memory.models import (
    MemoryDraft,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)


class MemoryModelTests(unittest.TestCase):
    def test_new_draft_is_candidate(self):
        draft = MemoryDraft(
            type=MemoryType.LESSON,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Use isolated DB ports",
            body="Integration tests must allocate isolated DB ports.",
        )
        record = draft.to_record(memory_id="mem-lesson-db-ports-a1b2c3d4")
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)

    def test_memory_id_is_stable_for_same_identity(self):
        a = MemoryDraft(
            type=MemoryType.INVARIANT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Backward compatible migrations",
            body="body one",
        )
        b = MemoryDraft(
            type=MemoryType.INVARIANT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Backward compatible migrations",
            body="body two",
        )
        self.assertEqual(a.suggested_id(), b.suggested_id())
