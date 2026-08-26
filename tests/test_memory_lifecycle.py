import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from nexus_harness.memory.lifecycle import (
    CandidateSignal,
    MemoryPromotionError,
    collect_memory_candidates,
    promote_to_portfolio_draft,
    supersede_memory,
    verify_memory,
    verify_record,
)
from nexus_harness.memory.models import (
    MemoryDraft,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.store import init_project_memory, read_memory, write_memory


def _write_source(root: Path, ref: str, body: str = "approved") -> None:
    if "/" in ref:
        path = root / ref
    elif ref.startswith("ADR-"):
        path = root / "docs" / "adr" / f"{ref}.md"
    elif ref.startswith("SPEC-"):
        path = root / "docs" / f"{ref}.md"
    else:
        path = root / "docs" / f"{ref}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _decision_draft(**overrides) -> MemoryDraft:
    payload = {
        "type": MemoryType.DECISION,
        "scope": MemoryScope.PROJECT,
        "project_id": "repo-1",
        "title": "Use queue X",
        "body": "Queue X is the selected transport.",
    }
    payload.update(overrides)
    return MemoryDraft(**payload)


class MemoryLifecycleTests(unittest.TestCase):
    def test_decision_without_authoritative_source_stays_candidate(self):
        record = _decision_draft().to_record()
        with self.assertRaises(MemoryPromotionError):
            verify_record(record, current_commit="abc")
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)

    def test_llm_summary_alone_is_not_provenance(self):
        record = _decision_draft(
            sources=(MemorySource("llm_summary", "model-said-so"),),
        ).to_record()
        with self.assertRaises(MemoryPromotionError):
            verify_record(record, current_commit="abc")
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)

    def test_decision_with_adr_can_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_source(root, "ADR-001")
            record = _decision_draft(
                sources=(MemorySource("adr", "ADR-001"),),
            ).to_record()
            verified = verify_record(record, current_commit="abc", project_root=root)
        self.assertEqual(verified.status, MemoryStatus.VERIFIED)
        self.assertEqual(verified.valid_at_commit, "abc")

    def test_self_declared_adr_without_file_cannot_verify(self):
        record = _decision_draft(
            sources=(MemorySource("adr", "ADR-001"),),
        ).to_record()
        with self.assertRaises(MemoryPromotionError):
            verify_record(record, current_commit="abc")

    def test_verify_record_does_not_mutate_frozen_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_source(root, "ADR-001")
            record = _decision_draft(
                sources=(MemorySource("adr", "ADR-001"),),
            ).to_record()
            snapshot = record.to_json_dict()
            verified = verify_record(record, current_commit="abc", project_root=root)
        self.assertEqual(record.to_json_dict(), snapshot)
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)
        self.assertIsNone(record.valid_at_commit)
        self.assertIsNot(verified, record)
        self.assertEqual(verified.status, MemoryStatus.VERIFIED)

    def test_collect_memory_candidates_ignores_tool_call_and_unknown_kinds(self):
        drafts = collect_memory_candidates(
            project_id="repo-1",
            task_id="task-9",
            signals=(
                CandidateSignal(
                    kind="tool_call",
                    title="ran pytest",
                    statement="pytest tests/foo.py -q && cat /etc/passwd",
                    sources=(),
                ),
                CandidateSignal(
                    kind="unknown",
                    title="transient note",
                    statement="agent guessed a refactor",
                    sources=(),
                ),
                CandidateSignal(
                    kind="architecture_decision",
                    title="Use queue X",
                    statement="Queue X is the selected transport.",
                    sources=(MemorySource("adr", "ADR-001"),),
                ),
            ),
        )
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].type, MemoryType.DECISION)
        self.assertEqual(drafts[0].title, "Use queue X")
        self.assertFalse(
            any(draft.body.startswith("pytest ") for draft in drafts),
        )

    def test_verify_memory_and_supersede_memory_persist_with_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            _write_source(root, "ADR-001")
            _write_source(root, "ADR-002")
            record = write_memory(
                root,
                _decision_draft(
                    sources=(MemorySource("adr", "ADR-001"),),
                ).to_record(),
            )
            verified = verify_memory(root, record.id, current_commit="abc")
            stored = read_memory(root, record.id)
            self.assertEqual(verified.status, MemoryStatus.VERIFIED)
            self.assertEqual(stored.status, MemoryStatus.VERIFIED)
            self.assertEqual(stored.valid_at_commit, "abc")

            replacement = write_memory(
                root,
                _decision_draft(
                    title="Use queue Y",
                    body="Queue Y replaces queue X.",
                    sources=(MemorySource("adr", "ADR-002"),),
                ).to_record(),
            )
            superseded = supersede_memory(root, record.id, replacement.id)
            reread = read_memory(root, record.id)
            self.assertEqual(superseded.status, MemoryStatus.SUPERSEDED)
            self.assertEqual(reread.status, MemoryStatus.SUPERSEDED)

    def test_supersede_memory_links_both_sides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            _write_source(root, "ADR-001")
            _write_source(root, "ADR-002")
            old = write_memory(
                root,
                _decision_draft(
                    title="Use queue X",
                    sources=(MemorySource("adr", "ADR-001"),),
                ).to_record(),
            )
            replacement = write_memory(
                root,
                _decision_draft(
                    title="Use queue Y",
                    body="Queue Y replaces queue X.",
                    sources=(MemorySource("adr", "ADR-002"),),
                ).to_record(),
            )

            supersede_memory(root, old.id, replacement.id)

            stored_old = read_memory(root, old.id)
            stored_new = read_memory(root, replacement.id)
            self.assertEqual(stored_old.status, MemoryStatus.SUPERSEDED)
            self.assertIn(replacement.id, stored_old.supersedes)
            self.assertIn(old.id, stored_new.supersedes)

            from nexus_harness.memory.doctor import memory_doctor

            report = memory_doctor(root)
            self.assertFalse(
                any(
                    finding.code == "superseded_without_target"
                    and finding.severity == "FAIL"
                    for finding in report.findings
                )
            )

    def test_promote_to_portfolio_draft_requires_verified_project_source(self):
        candidate = _decision_draft(
            sources=(MemorySource("adr", "ADR-001"),),
        ).to_record()
        with self.assertRaises(MemoryPromotionError):
            promote_to_portfolio_draft(
                (candidate,),
                title="Cross-project queue choice",
                body="Queue X is reusable across projects.",
                tags=("queue",),
            )

        verified = replace(
            candidate,
            status=MemoryStatus.VERIFIED,
            valid_at_commit="abc",
        )
        draft = promote_to_portfolio_draft(
            (verified,),
            title="Cross-project queue choice",
            body="Queue X is reusable across projects.",
            tags=("queue",),
        )
        self.assertEqual(draft.scope, MemoryScope.PORTFOLIO)
        self.assertIsNone(draft.project_id)
        self.assertEqual(
            draft.sources,
            (MemorySource("project_memory", verified.id),),
        )
        self.assertEqual(draft.to_record().status, MemoryStatus.CANDIDATE)

    def test_promote_to_portfolio_draft_sources_only_verified_project_ids(self):
        verified = replace(
            _decision_draft(
                title="Use queue X",
                sources=(MemorySource("adr", "ADR-001"),),
            ).to_record(),
            status=MemoryStatus.VERIFIED,
            valid_at_commit="abc",
        )
        sibling_candidate = _decision_draft(
            title="Use queue Y",
            sources=(MemorySource("adr", "ADR-002"),),
        ).to_record()
        other_candidate = _decision_draft(
            title="Use queue Z",
            sources=(MemorySource("adr", "ADR-003"),),
        ).to_record()
        draft = promote_to_portfolio_draft(
            (sibling_candidate, verified, other_candidate),
            title="Cross-project queue choice",
            body="Queue X is reusable across projects.",
            tags=("queue",),
        )
        self.assertEqual(
            draft.sources,
            (MemorySource("project_memory", verified.id),),
        )

    def test_pattern_needs_two_distinct_source_refs_unless_approved_spec_or_adr(self):
        single = MemoryDraft(
            type=MemoryType.PATTERN,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Idempotent webhook consumers",
            body="Webhook consumers require stable idempotency keys.",
            sources=(MemorySource("review_finding", "rev-1"),),
        ).to_record()
        with self.assertRaises(MemoryPromotionError):
            verify_record(single, current_commit="abc")

        duplicate_ref = replace(
            single,
            sources=(
                MemorySource("review_finding", "rev-1"),
                MemorySource("bug_card", "rev-1"),
            ),
        )
        with self.assertRaises(MemoryPromotionError):
            verify_record(duplicate_ref, current_commit="abc")

        two_refs = replace(
            single,
            sources=(
                MemorySource("review_finding", "rev-1"),
                MemorySource("bug_card", "bug-2"),
            ),
        )
        verified = verify_record(two_refs, current_commit="abc")
        self.assertEqual(verified.status, MemoryStatus.VERIFIED)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_source(root, "ADR-014")
            _write_source(root, "SPEC-2")
            with_adr = replace(single, sources=(MemorySource("adr", "ADR-014"),))
            self.assertEqual(
                verify_record(with_adr, current_commit="abc", project_root=root).status,
                MemoryStatus.VERIFIED,
            )
            with_spec = replace(
                single, sources=(MemorySource("approved_spec", "SPEC-2"),)
            )
            self.assertEqual(
                verify_record(
                    with_spec, current_commit="abc", project_root=root
                ).status,
                MemoryStatus.VERIFIED,
            )

    def test_pattern_two_llm_summary_sources_cannot_verify(self):
        record = MemoryDraft(
            type=MemoryType.PATTERN,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Idempotent webhook consumers",
            body="Webhook consumers require stable idempotency keys.",
            sources=(
                MemorySource("llm_summary", "sum-1"),
                MemorySource("llm_summary", "sum-2"),
            ),
        ).to_record()
        with self.assertRaises(MemoryPromotionError):
            verify_record(record, current_commit="abc")
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)

    def test_pattern_two_distinct_same_kind_evidence_refs_can_verify(self):
        record = MemoryDraft(
            type=MemoryType.PATTERN,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Idempotent webhook consumers",
            body="Webhook consumers require stable idempotency keys.",
            sources=(
                MemorySource("review_finding", "rev-1"),
                MemorySource("review_finding", "rev-2"),
            ),
        ).to_record()

        verified = verify_record(record, current_commit="abc")

        self.assertEqual(verified.status, MemoryStatus.VERIFIED)

    def test_deterministic_evidence_failing_exit_or_diff_stays_unpromoted(self):
        record = MemoryDraft(
            type=MemoryType.INVARIANT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Migrations stay backward compatible",
            body="Production migrations remain backward compatible.",
            sources=(MemorySource("deterministic_evidence", "ev-77"),),
            evidence_ids=("ev-77",),
        ).to_record()

        def failing_exit(_evidence_id: str) -> dict:
            return {"exit_code": 1, "diff": "same"}

        def mismatched_diff(_evidence_id: str) -> dict:
            return {"exit_code": 0, "diff": "stored-diff"}

        with self.assertRaises(MemoryPromotionError):
            verify_record(
                record,
                current_commit="abc",
                evidence_lookup=failing_exit,
                current_diff="same",
            )
        with self.assertRaises(MemoryPromotionError):
            verify_record(
                record,
                current_commit="abc",
                evidence_lookup=mismatched_diff,
                current_diff="current-diff",
            )
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)

    def test_deterministic_evidence_empty_evidence_ids_cannot_verify(self):
        record = MemoryDraft(
            type=MemoryType.INVARIANT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Migrations stay backward compatible",
            body="Production migrations remain backward compatible.",
            sources=(MemorySource("deterministic_evidence", "ev-77"),),
            evidence_ids=(),
        ).to_record()
        with self.assertRaises(MemoryPromotionError):
            verify_record(record, current_commit="abc")
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)

    def test_deterministic_evidence_lookup_none_cannot_verify(self):
        record = MemoryDraft(
            type=MemoryType.INVARIANT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Migrations stay backward compatible",
            body="Production migrations remain backward compatible.",
            sources=(MemorySource("deterministic_evidence", "ev-77"),),
            evidence_ids=("ev-77",),
        ).to_record()
        with self.assertRaises(MemoryPromotionError):
            verify_record(
                record,
                current_commit="abc",
                evidence_lookup=None,
            )

    def test_component_requires_existing_related_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "auth.py").write_text("ok", encoding="utf-8")
            missing = MemoryDraft(
                type=MemoryType.COMPONENT,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Auth",
                body="Auth lives in src/auth.py",
                sources=(MemorySource("canonical_doc", "docs/auth.md"),),
                related_paths=("src/missing.py",),
            ).to_record()
            _write_source(root, "docs/auth.md")
            with self.assertRaises(MemoryPromotionError):
                verify_record(missing, current_commit="abc", project_root=root)
            present = MemoryDraft(
                type=MemoryType.COMPONENT,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Auth",
                body="Auth lives in src/auth.py",
                sources=(MemorySource("canonical_doc", "docs/auth.md"),),
                related_paths=("src/auth.py",),
            ).to_record()
            verified = verify_record(present, current_commit="abc", project_root=root)
            self.assertEqual(verified.status, MemoryStatus.VERIFIED)
