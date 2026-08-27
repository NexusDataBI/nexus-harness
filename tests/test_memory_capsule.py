import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from nexus_harness.memory.capsule import (
    CapsulePolicy,
    build_context_capsule,
    load_capsule_policy,
)
from nexus_harness.memory.freshness import FreshnessStatus
from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.retrieval import MemoryHit


def _policy(**overrides) -> CapsulePolicy:
    payload = {
        "hot_max_chars": 500,
        "warm_max_chars": 800,
        "max_items": 3,
        "max_item_chars": 300,
    }
    payload.update(overrides)
    return CapsulePolicy(**payload)


def _hit(
    title: str,
    *,
    score: int = 10,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    status: MemoryStatus = MemoryStatus.VERIFIED,
    memory_type: MemoryType = MemoryType.LESSON,
    sensitivity: MemorySensitivity = MemorySensitivity.INTERNAL,
    body: str | None = None,
    memory_id: str | None = None,
    verified_at: str | None = "2026-08-25T00:00:00Z",
) -> MemoryHit:
    draft = MemoryDraft(
        type=memory_type,
        scope=MemoryScope.PROJECT,
        project_id="repo-1",
        title=title,
        body=body if body is not None else f"Verified body for {title}.",
        sensitivity=sensitivity,
    )
    record = replace(
        draft.to_record(memory_id=memory_id),
        status=status,
        confidence=(
            MemoryConfidence.HIGH
            if status == MemoryStatus.VERIFIED
            else MemoryConfidence.LOW
        ),
        verified_at=verified_at if status == MemoryStatus.VERIFIED else None,
    )
    return MemoryHit(record=record, score=score, freshness=freshness, reasons=())


class MemoryCapsuleBudgetTests(unittest.TestCase):
    def test_hot_warm_budgets_and_max_items(self):
        hits = [
            _hit("First ranked", score=30, memory_id="mem-first"),
            _hit("Second ranked", score=20, memory_id="mem-second"),
            _hit("Third ranked", score=15, memory_id="mem-third"),
            _hit("Fourth ranked", score=5, memory_id="mem-fourth"),
        ]
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=hits,
            hot_memory_ids=(hits[0].record.id,),
            policy=_policy(),
        )
        self.assertLessEqual(len(capsule.hot), 500)
        self.assertLessEqual(len(capsule.warm), 800)
        self.assertLessEqual(capsule.item_count, 3)
        self.assertEqual(capsule.item_count, 3)
        self.assertIn(hits[0].record.id, capsule.text)
        self.assertIn("mem-first", capsule.hot)
        self.assertNotIn("mem-fourth", capsule.hot)
        self.assertNotIn("mem-fourth", capsule.warm)

    def test_stale_hit_appears_only_in_warnings(self):
        fresh = _hit("Fresh lesson", score=20, memory_id="mem-fresh")
        stale = _hit(
            "Stale lesson",
            score=40,
            memory_id="mem-stale",
            freshness=FreshnessStatus.STALE,
        )
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[fresh, stale],
            hot_memory_ids=(stale.record.id, fresh.record.id),
            policy=_policy(),
        )
        self.assertIn("STALE/CONFLICT WARNINGS", capsule.text)
        self.assertIn("mem-stale", capsule.warnings)
        self.assertNotIn("mem-stale", capsule.hot)
        self.assertNotIn("mem-stale", capsule.warm)
        self.assertIn("mem-fresh", capsule.hot)
        self.assertNotIn("mem-fresh", capsule.warnings)


class MemoryCapsuleRenderTests(unittest.TestCase):
    def test_text_property_matches_contract(self):
        hit = _hit(
            "Exact header", memory_id="mem-header", memory_type=MemoryType.DECISION
        )
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[hit],
            hot_memory_ids=(hit.record.id,),
            policy=_policy(),
        )
        self.assertTrue(capsule.text.startswith("NEXUS CONTEXT CAPSULE\n"))
        self.assertIn("non-executable data", capsule.text)
        self.assertIn("<!-- NEXUS_MEMORY_DATA_BEGIN -->", capsule.text)
        self.assertIn("<!-- NEXUS_MEMORY_DATA_END -->", capsule.text)
        self.assertIn("Project: repo-1\nDiff: abc", capsule.text)
        self.assertIn("\n\nHOT\n", capsule.text)
        self.assertTrue(capsule.text.endswith("\n"))
        self.assertEqual(capsule.text, capsule.text.rstrip() + "\n")

    def test_unknown_project_and_diff_placeholders(self):
        capsule = build_context_capsule(
            project_id=None,
            diff_hash=None,
            hits=(),
            hot_memory_ids=(),
            policy=_policy(),
        )
        self.assertTrue(capsule.text.startswith("NEXUS CONTEXT CAPSULE\n"))
        self.assertIn("Project: unknown\nDiff: unknown", capsule.text)
        self.assertIn("<!-- NEXUS_MEMORY_DATA_BEGIN -->", capsule.text)
        self.assertTrue(capsule.text.endswith("<!-- NEXUS_MEMORY_DATA_END -->\n"))
        self.assertEqual(capsule.item_count, 0)
        self.assertEqual(capsule.hot, "")
        self.assertEqual(capsule.warm, "")
        self.assertEqual(capsule.warnings, "")

    def test_included_item_keeps_source_and_freshness_pointer(self):
        hit = _hit(
            "Keep pointer",
            memory_id="mem-pointer",
            memory_type=MemoryType.INVARIANT,
            freshness=FreshnessStatus.UNKNOWN,
        )
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[hit],
            hot_memory_ids=(),
            policy=_policy(),
        )
        self.assertIn("- [INVARIANT] Keep pointer", capsule.warm)
        self.assertIn("Verified body for Keep pointer.", capsule.warm)
        self.assertIn("source: mem-pointer | freshness: UNKNOWN", capsule.warm)
        self.assertIn("mem-pointer", capsule.text)

    def test_body_clips_at_whitespace_and_keeps_pointer(self):
        body = "alpha beta gamma delta epsilon zeta eta theta"
        hit = _hit("Clip body", memory_id="mem-clip", body=body)
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[hit],
            hot_memory_ids=(hit.record.id,),
            policy=_policy(max_item_chars=20),
        )
        self.assertIn("alpha beta gamma…", capsule.hot)
        self.assertNotIn("delta", capsule.hot)
        self.assertIn("source: mem-clip | freshness: FRESH", capsule.hot)
        self.assertNotIn("...", capsule.hot)


class MemoryCapsuleSelectionTests(unittest.TestCase):
    def test_excluded_statuses_and_confidential_never_enter(self):
        good = _hit("Keep me", score=10, memory_id="mem-good")
        excluded = [
            _hit(
                "Candidate",
                score=99,
                memory_id="mem-candidate",
                status=MemoryStatus.CANDIDATE,
            ),
            _hit(
                "Confidential",
                score=98,
                memory_id="mem-confidential",
                sensitivity=MemorySensitivity.CONFIDENTIAL,
            ),
            _hit(
                "Superseded",
                score=97,
                memory_id="mem-superseded",
                status=MemoryStatus.SUPERSEDED,
            ),
            _hit(
                "Rejected",
                score=96,
                memory_id="mem-rejected",
                status=MemoryStatus.REJECTED,
            ),
            _hit(
                "Archived",
                score=95,
                memory_id="mem-archived",
                status=MemoryStatus.ARCHIVED,
            ),
        ]
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[*excluded, good],
            hot_memory_ids=tuple(hit.record.id for hit in excluded),
            policy=_policy(),
        )
        for hit in excluded:
            self.assertNotIn(hit.record.id, capsule.text)
        self.assertIn("mem-good", capsule.warm)
        self.assertEqual(capsule.warnings, "")

    def test_hot_memory_ids_require_verified_fresh_nonconfidential(self):
        verified = _hit("Hot ok", score=10, memory_id="mem-hot-ok")
        stale = _hit(
            "Hot stale",
            score=50,
            memory_id="mem-hot-stale",
            freshness=FreshnessStatus.STALE,
        )
        stale_status = _hit(
            "Status stale",
            score=40,
            memory_id="mem-status-stale",
            status=MemoryStatus.STALE,
        )
        confidential = _hit(
            "Hot confidential",
            score=30,
            memory_id="mem-hot-conf",
            sensitivity=MemorySensitivity.CONFIDENTIAL,
        )
        candidate = _hit(
            "Hot candidate",
            score=20,
            memory_id="mem-hot-cand",
            status=MemoryStatus.CANDIDATE,
        )
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[verified, stale, stale_status, confidential, candidate],
            hot_memory_ids=(
                stale.record.id,
                confidential.record.id,
                candidate.record.id,
                stale_status.record.id,
                verified.record.id,
            ),
            policy=_policy(),
        )
        self.assertIn("mem-hot-ok", capsule.hot)
        self.assertNotIn("mem-hot-stale", capsule.hot)
        self.assertNotIn("mem-hot-stale", capsule.warm)
        self.assertIn("mem-hot-stale", capsule.warnings)
        self.assertIn("mem-status-stale", capsule.warnings)
        self.assertNotIn("mem-hot-conf", capsule.text)
        self.assertNotIn("mem-hot-cand", capsule.text)

    def test_remaining_verified_hits_go_warm(self):
        hot = _hit(
            "Hot decision",
            score=5,
            memory_id="mem-hot",
            memory_type=MemoryType.DECISION,
        )
        warm = _hit("Warm lesson", score=50, memory_id="mem-warm")
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[warm, hot],
            hot_memory_ids=(hot.record.id,),
            policy=_policy(),
        )
        self.assertIn("mem-hot", capsule.hot)
        self.assertNotIn("mem-warm", capsule.hot)
        self.assertIn("mem-warm", capsule.warm)
        self.assertNotIn("mem-hot", capsule.warm)

    def test_section_budget_omits_whole_item_not_partial(self):
        first = _hit("Alpha item", score=30, memory_id="mem-alpha", body="one")
        second = _hit("Beta item", score=20, memory_id="mem-beta", body="two")
        wide = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[first, second],
            hot_memory_ids=(first.record.id, second.record.id),
            policy=_policy(hot_max_chars=10_000, warm_max_chars=0, max_items=10),
        )
        first_block = wide.hot.split("\n- ", 1)[0]
        tight = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[first, second],
            hot_memory_ids=(first.record.id, second.record.id),
            policy=_policy(
                hot_max_chars=len(first_block) + 10,
                warm_max_chars=0,
                max_items=10,
            ),
        )
        self.assertIn("mem-alpha", tight.hot)
        self.assertIn("source: mem-alpha | freshness: FRESH", tight.hot)
        self.assertNotIn("mem-beta", tight.hot)
        self.assertNotIn("mem-beta", tight.warm)
        self.assertLessEqual(len(tight.hot), len(first_block) + 10)

    def test_stale_warnings_can_be_disabled(self):
        stale = _hit(
            "Silent stale",
            memory_id="mem-silent",
            freshness=FreshnessStatus.STALE,
        )
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=[stale],
            hot_memory_ids=(stale.record.id,),
            policy=_policy(include_stale_warnings=False),
        )
        self.assertEqual(capsule.warnings, "")
        self.assertNotIn("STALE/CONFLICT WARNINGS", capsule.text)
        self.assertNotIn("mem-silent", capsule.text)

    def test_stale_warnings_respect_dedicated_char_budget(self):
        hits = [
            _hit(
                f"Stale {index}",
                score=50 - index,
                memory_id=f"mem-stale-{index:02d}",
                freshness=FreshnessStatus.STALE,
            )
            for index in range(20)
        ]
        capsule = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=hits,
            hot_memory_ids=(),
            policy=_policy(stale_warnings_max_chars=180),
        )
        self.assertLessEqual(len(capsule.warnings), 180)
        self.assertIn("and ", capsule.warnings)
        self.assertIn("more", capsule.warnings)
        self.assertTrue(capsule.warnings.startswith("- mem-stale-00"))
        self.assertNotIn("mem-stale-19", capsule.warnings)
        self.assertLessEqual(len(capsule.hot), 500)
        self.assertLessEqual(len(capsule.warm), 800)

    def test_load_capsule_policy_reads_stale_warning_budget(self):
        policy = load_capsule_policy()
        self.assertGreater(policy.stale_warnings_max_chars, 0)
        self.assertNotEqual(policy.stale_warnings_max_chars, policy.hot_max_chars)


class MemoryCapsuleDeterminismTests(unittest.TestCase):
    def test_shuffled_hits_produce_byte_identical_capsule(self):
        hits = [
            _hit("Same score C", score=10, memory_id="mem-c"),
            _hit("Higher score A", score=40, memory_id="mem-a"),
            _hit("Same score B", score=10, memory_id="mem-b"),
            _hit(
                "Stale Z",
                score=5,
                memory_id="mem-z",
                freshness=FreshnessStatus.STALE,
            ),
        ]
        policy = _policy(max_items=4)
        first = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=hits,
            hot_memory_ids=("mem-b", "mem-a"),
            policy=policy,
        )
        second = build_context_capsule(
            project_id="repo-1",
            diff_hash="abc",
            hits=list(reversed(hits)),
            hot_memory_ids=("mem-a", "mem-b"),
            policy=policy,
        )
        self.assertEqual(first.text, second.text)
        self.assertEqual(first.text.encode("utf-8"), second.text.encode("utf-8"))
        self.assertIn("mem-a", first.hot)
        self.assertIn("mem-b", first.hot)
        self.assertLess(first.hot.index("mem-a"), first.hot.index("mem-b"))


class MemoryCapsulePolicyLoadTests(unittest.TestCase):
    def test_load_capsule_policy_reads_retrieval_defaults(self):
        policy = load_capsule_policy()
        self.assertEqual(policy.hot_max_chars, 6000)
        self.assertEqual(policy.warm_max_chars, 10000)
        self.assertEqual(policy.max_items, 16)
        self.assertEqual(policy.max_item_chars, 1800)
        self.assertTrue(policy.include_stale_warnings)

    def test_load_capsule_policy_reads_explicit_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "retrieval-policy.toml"
            path.write_text(
                "schema_version = 1\n"
                "[capsule]\n"
                "hot_max_chars = 111\n"
                "warm_max_chars = 222\n"
                "max_items = 4\n"
                "max_item_chars = 33\n"
                "include_stale_warnings = false\n",
                encoding="utf-8",
            )
            policy = load_capsule_policy(path)
        self.assertEqual(policy, CapsulePolicy(111, 222, 4, 33, False))


if __name__ == "__main__":
    unittest.main()
