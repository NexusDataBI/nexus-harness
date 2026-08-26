import unittest
from unittest.mock import patch

from nexus_harness.completion import CompletionResult
from nexus_harness.pull_request import ready_to_merge, render_pr_body


def _pass_report(diff_hash="abc"):
    return {"gate": "PASS", "diff_hash": diff_hash, "report": "structured"}


def _ready_state(**overrides):
    state = {
        "tracking_required": True,
        "issue": 123,
        "acceptance": [{"id": "AC-1", "status": "PASS", "evidence": "ev-1"}],
        "quality_gate": _pass_report(),
        "security_gate": _pass_report(),
        "review_gate": "PASS",
        "current_diff_hash": "abc",
        "verified_diff_hash": "abc",
        "reviewed_diff_hash": "abc",
        "evidence": [{"id": "ev-1", "exit_code": 0, "diff_hash": "abc"}],
        "findings": [],
    }
    state.update(overrides)
    return state


class PullRequestTests(unittest.TestCase):
    def test_complete_issue_uses_closes_reference(self):
        body = render_pr_body(issue=123, partial=False, summary="Fix", evidence=[])
        self.assertIn("Closes #123", body)

    def test_partial_issue_uses_refs_reference(self):
        body = render_pr_body(issue=123, partial=True, summary="WIP", evidence=[])
        self.assertIn("Refs #123", body)
        self.assertNotIn("Closes #123", body)

    def test_pr_body_contains_required_sections(self):
        body = render_pr_body(issue=7, summary="Fix login")
        for heading in (
            "Summary",
            "Issue",
            "Scope",
            "Acceptance",
            "Verification",
            "Quality",
            "Security",
            "Deployment impact",
            "Known limitations",
        ):
            self.assertIn(f"## {heading}", body)
        self.assertNotIn("## Frontend evidence", body)

    def test_frontend_evidence_included_when_applicable(self):
        body = render_pr_body(
            issue=7,
            summary="UI",
            frontend=True,
            frontend_evidence="desktop + mobile screenshots",
        )
        self.assertIn("## Frontend evidence", body)
        self.assertIn("desktop + mobile screenshots", body)

    def test_failed_quality_blocks_merge(self):
        result = ready_to_merge(
            _ready_state(quality_gate={"gate": "FAIL", "diff_hash": "abc"})
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("quality" in reason for reason in result.reasons))

    def test_ready_to_merge_reuses_evaluate_completion(self):
        state = {"issue": 1}
        with patch(
            "nexus_harness.pull_request.evaluate_completion",
            return_value=CompletionResult(status="READY_TO_SHIP", reasons=[]),
        ) as evaluate:
            result = ready_to_merge(state)
        evaluate.assert_called_once_with(state)
        self.assertEqual(result.status, "READY_TO_MERGE")
        self.assertEqual(result.reasons, [])

    def test_missing_issue_blocks_merge_when_tracking_required(self):
        result = ready_to_merge(_ready_state(issue=None))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("issue" in reason for reason in result.reasons))

    def test_acceptance_incomplete_blocks_merge(self):
        result = ready_to_merge(
            _ready_state(acceptance=[{"id": "AC-1", "status": "FAIL"}])
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("acceptance" in reason for reason in result.reasons))

    def test_fresh_evidence_missing_blocks_merge(self):
        result = ready_to_merge(
            _ready_state(
                current_diff_hash="def",
                verified_diff_hash="def",
                reviewed_diff_hash="def",
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("evidence" in reason for reason in result.reasons))

    def test_security_fail_blocks_merge(self):
        result = ready_to_merge(
            _ready_state(security_gate={"gate": "FAIL", "diff_hash": "abc"})
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("security" in reason for reason in result.reasons))

    def test_review_fail_blocks_merge(self):
        result = ready_to_merge(_ready_state(review_gate="FAIL"))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("review" in reason for reason in result.reasons))

    def test_blocker_or_high_blocks_merge(self):
        result = ready_to_merge(
            _ready_state(findings=[{"severity": "high", "confirmed": True}])
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("finding" in reason or "high" in reason for reason in result.reasons)
        )

    def test_stale_reviewed_or_verified_diff_blocks_merge(self):
        result = ready_to_merge(_ready_state(verified_diff_hash="zzz"))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("diff_hash" in reason for reason in result.reasons))

    def test_draft_allowed_before_green(self):
        result = ready_to_merge(
            _ready_state(quality_gate={"gate": "FAIL", "diff_hash": "abc"})
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(result.draft_allowed)

    def test_ready_state_is_ready_to_merge(self):
        result = ready_to_merge(_ready_state())
        self.assertEqual(result.status, "READY_TO_MERGE")
        self.assertEqual(result.reasons, [])
        self.assertTrue(result.draft_allowed)
