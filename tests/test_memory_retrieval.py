import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryRecord,
    MemoryScope,
    MemorySensitivity,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.freshness import AuthorityContradiction, TruthStrength
from nexus_harness.memory.retrieval import (
    MemoryQueryContext,
    default_index_path,
    fts5_available,
    rebuild_index,
    search_memory,
)
from nexus_harness.memory.store import (
    init_project_memory,
    load_project_memories,
    write_memory,
)


def _draft(title: str, **overrides) -> MemoryDraft:
    payload = {
        "type": MemoryType.LESSON,
        "scope": MemoryScope.PROJECT,
        "project_id": "repo-1",
        "title": title,
        "body": "Recall boundary behavior.",
        "sources": (MemorySource("approved_spec", "SPEC-1"),),
    }
    payload.update(overrides)
    return MemoryDraft(**payload)


def _verified_record(title: str, **overrides) -> MemoryRecord:
    payload = {
        "status": MemoryStatus.VERIFIED,
        "confidence": MemoryConfidence.HIGH,
        "verified_at": "2026-08-25T00:00:00Z",
    }
    payload.update(overrides)
    return replace(_draft(title).to_record(), **payload)


class MemoryRetrievalExclusionTests(unittest.TestCase):
    def _search_with(self, excluded_record):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            cache_home = root / "cache"
            init_project_memory(project_root)
            included = write_memory(
                project_root,
                _verified_record("Recall included control"),
            )
            write_memory(project_root, excluded_record)

            hits = search_memory(
                project_root,
                "recall",
                MemoryQueryContext(project_id="repo-1", include_stale=False),
                cache_home=cache_home,
            )

            return included.id, [hit.record.id for hit in hits]

    def test_normal_recall_excludes_candidate_from_default_draft_record(self):
        candidate = _draft("Recall candidate excluded").to_record()

        included_id, hit_ids = self._search_with(candidate)

        self.assertEqual(hit_ids, [included_id])
        self.assertNotIn(candidate.id, hit_ids)

    def test_normal_recall_excludes_confidential_even_when_verified(self):
        confidential = _verified_record(
            "Recall confidential excluded",
            sensitivity=MemorySensitivity.CONFIDENTIAL,
        )

        included_id, hit_ids = self._search_with(confidential)

        self.assertEqual(hit_ids, [included_id])
        self.assertNotIn(confidential.id, hit_ids)

    def test_normal_recall_excludes_stale_when_include_stale_is_false(self):
        stale = replace(
            _draft("Recall stale excluded").to_record(),
            status=MemoryStatus.STALE,
        )

        included_id, hit_ids = self._search_with(stale)

        self.assertEqual(hit_ids, [included_id])
        self.assertNotIn(stale.id, hit_ids)

    def test_current_repo_contradiction_excludes_verified_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            contradicted = write_memory(
                root,
                _verified_record("Contradicted auth rule"),
            )

            hits = search_memory(
                root,
                "contradicted auth",
                MemoryQueryContext(
                    project_id="repo-1",
                    contradictions=(
                        AuthorityContradiction(
                            memory_id=contradicted.id,
                            authority=TruthStrength.CURRENT_REPO,
                            pointer="src/auth/session.py",
                        ),
                    ),
                ),
                cache_home=root / "cache",
            )

            self.assertNotIn(contradicted.id, [hit.record.id for hit in hits])

    def test_weaker_authority_does_not_exclude_verified_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = write_memory(root, _verified_record("Retained auth rule"))

            hits = search_memory(
                root,
                "retained auth",
                MemoryQueryContext(
                    project_id="repo-1",
                    contradictions=(
                        AuthorityContradiction(
                            memory_id=record.id,
                            authority=TruthStrength.VERIFIED_PORTFOLIO_MEMORY,
                            pointer="portfolio/fact.md",
                        ),
                    ),
                ),
                cache_home=root / "cache",
            )

            self.assertIn(record.id, [hit.record.id for hit in hits])


def _verified(record):
    sources = record.sources or (MemorySource("approved_spec", "SPEC-1"),)
    return replace(
        record,
        status=MemoryStatus.VERIFIED,
        confidence=MemoryConfidence.HIGH,
        sources=sources,
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

    def test_fts_does_not_drop_path_matching_record_without_query_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_home = root / "cache"
            init_project_memory(root)
            path_hit = _verified(
                MemoryDraft(
                    type=MemoryType.INVARIANT,
                    scope=MemoryScope.PROJECT,
                    project_id="repo-1",
                    title="Auth session isolation",
                    body="Session cookies stay isolated per tenant.",
                    related_paths=("src/auth/**",),
                    tags=("auth",),
                    sources=(MemorySource("approved_spec", "SPEC-AUTH"),),
                ).to_record()
            )
            decoy = _verified(
                MemoryDraft(
                    type=MemoryType.LESSON,
                    scope=MemoryScope.PROJECT,
                    project_id="repo-1",
                    title="zzzz-no-token decoy",
                    body="This decoy mentions zzzz-no-token so FTS MATCH is non-empty.",
                    tags=("unrelated",),
                    sources=(MemorySource("review_finding", "rev-1"),),
                ).to_record()
            )
            write_memory(root, path_hit)
            write_memory(root, decoy)
            hits = search_memory(
                root,
                "zzzz-no-token",
                MemoryQueryContext(
                    project_id="repo-1",
                    affected_paths=("src/auth/session.py",),
                    tags=("auth",),
                ),
                cache_home=cache_home,
            )
            hit_ids = [hit.record.id for hit in hits]
            self.assertIn(path_hit.id, hit_ids)
            path_reasons = next(
                hit.reasons for hit in hits if hit.record.id == path_hit.id
            )
            self.assertTrue(
                {"exact_path", "path_prefix"} & set(path_reasons),
                path_reasons,
            )
            if fts5_available():
                self.assertIn(decoy.id, hit_ids)
