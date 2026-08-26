import unittest

from nexus_harness.completion import evaluate_completion, promote_acceptance
from nexus_harness.evidence import Evidence
from nexus_harness.quality import QualityReport
from nexus_harness.security import SecurityReport
from nexus_harness.state import AcceptanceCriterion, TaskState
from nexus_harness.workflow import advance_stage


def _pass_report(diff_hash="abc"):
    return {"gate": "PASS", "diff_hash": diff_hash, "report": "structured"}


def _visual_ev(viewport, diff_hash="abc", **overrides):
    payload = {
        "route": "/",
        "viewport": viewport,
        "diff_hash": diff_hash,
        "screenshot": f"{viewport}-after.png",
        "baseline": f"{viewport}-before.png",
        "trace": f"{viewport}.zip",
        "console_error_count": 0,
        "failed_request_count": 0,
        "reviewer_status": "PASS",
    }
    payload.update(overrides)
    return payload


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


class CompletionTests(unittest.TestCase):
    def test_failing_acceptance_blocks_done(self):
        state = {
            "tracking_required": True,
            "issue": 123,
            "acceptance": [{"id": "AC-1", "status": "FAIL"}],
            "quality_gate": _pass_report(),
            "security_gate": _pass_report(),
            "review_gate": "PASS",
            "current_diff_hash": "abc",
        }
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertIn("acceptance", result.reasons[0])

    def test_stale_evidence_blocks_done(self):
        state = _ready_state(
            current_diff_hash="def",
            verified_diff_hash="def",
            reviewed_diff_hash="def",
        )
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("evidence" in reason for reason in result.reasons))

    def test_confirmed_high_finding_blocks_done(self):
        state = _ready_state(
            findings=[{"severity": "high", "confirmed": True}],
        )
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("finding" in reason or "high" in reason for reason in result.reasons)
        )

    def test_status_confirmed_high_finding_blocks_done(self):
        result = evaluate_completion(
            _ready_state(findings=[{"severity": "high", "status": "confirmed"}])
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("finding" in reason or "high" in reason for reason in result.reasons)
        )

    def test_status_suspected_or_rejected_high_finding_does_not_block(self):
        for status in ("suspected", "rejected"):
            result = evaluate_completion(
                _ready_state(findings=[{"severity": "high", "status": status}])
            )
            self.assertEqual(
                result.status,
                "READY_TO_SHIP",
                msg=f"status={status} reasons={result.reasons}",
            )

    def test_quality_report_without_diff_hash_is_not_fresh(self):
        result = evaluate_completion(
            _ready_state(quality_gate=QualityReport(gate="PASS"))
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("quality" in reason and "fresh" in reason for reason in result.reasons)
        )

    def test_security_report_without_diff_hash_is_not_fresh(self):
        result = evaluate_completion(
            _ready_state(security_gate=SecurityReport(gate="PASS"))
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("security" in reason and "fresh" in reason for reason in result.reasons)
        )

    def test_quality_report_with_matching_diff_hash_is_ready(self):
        result = evaluate_completion(
            _ready_state(quality_gate=QualityReport(gate="PASS", diff_hash="abc"))
        )
        self.assertEqual(result.status, "READY_TO_SHIP")
        self.assertEqual(result.reasons, [])

    def test_blank_status_falls_through_to_confirmed_flag(self):
        result = evaluate_completion(
            _ready_state(
                findings=[{"severity": "high", "confirmed": True, "status": ""}]
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("finding" in reason or "high" in reason for reason in result.reasons)
        )

    def test_stale_quality_report_diff_hash_blocks_done(self):
        state = _ready_state(
            current_diff_hash="def",
            verified_diff_hash="def",
            reviewed_diff_hash="def",
            evidence=[{"id": "ev-1", "exit_code": 0, "diff_hash": "def"}],
            quality_gate=QualityReport(gate="PASS", diff_hash="abc"),
        )
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertNotEqual(result.status, "READY_TO_SHIP")
        self.assertTrue(
            any("quality" in reason and "fresh" in reason for reason in result.reasons)
        )

    def test_stale_security_report_diff_hash_blocks_done(self):
        state = _ready_state(
            current_diff_hash="def",
            verified_diff_hash="def",
            reviewed_diff_hash="def",
            evidence=[{"id": "ev-1", "exit_code": 0, "diff_hash": "def"}],
            security_gate=SecurityReport(gate="PASS", diff_hash="abc"),
        )
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertNotEqual(result.status, "READY_TO_SHIP")
        self.assertTrue(
            any("security" in reason and "fresh" in reason for reason in result.reasons)
        )

    def test_stale_quality_dict_diff_hash_blocks_done(self):
        state = _ready_state(
            current_diff_hash="def",
            verified_diff_hash="def",
            reviewed_diff_hash="def",
            evidence=[{"id": "ev-1", "exit_code": 0, "diff_hash": "def"}],
            quality_gate={"gate": "PASS", "diff_hash": "abc"},
        )
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("quality" in reason and "fresh" in reason for reason in result.reasons)
        )

    def test_negative_issue_does_not_satisfy_tracking(self):
        result = evaluate_completion(_ready_state(issue=-1))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("issue" in reason for reason in result.reasons))

    def test_promote_acceptance_from_fresh_evidence(self):
        state = {
            "current_diff_hash": "abc",
            "acceptance": [
                {"id": "AC-1", "status": "FAIL", "statement": "does the thing"}
            ],
        }
        evidence = Evidence("ev-1", "vitest", 0, "abc", "base-1", "tests pass")
        state["evidence"] = [evidence]
        promote_acceptance(state, evidence)
        self.assertEqual(state["acceptance"][0]["status"], "PASS")
        self.assertEqual(state["acceptance"][0]["evidence"], "ev-1")

    def test_cannot_promote_with_unrecorded_evidence_object(self):
        state = {
            "current_diff_hash": "abc",
            "acceptance": [
                {"id": "AC-1", "status": "FAIL", "statement": "does the thing"}
            ],
        }
        evidence = Evidence("ev-1", "vitest", 0, "abc", "base-1", "tests pass")
        with self.assertRaisesRegex(ValueError, "recorded"):
            promote_acceptance(state, evidence)
        self.assertEqual(state["acceptance"][0]["status"], "FAIL")

    def test_promote_acceptance_from_passed_ledger(self):
        state = {
            "current_diff_hash": "abc",
            "acceptance": [
                {"id": "AC-1", "status": "FAIL", "statement": "does the thing"}
            ],
        }
        evidence = Evidence("ev-1", "vitest", 0, "abc", "base-1", "tests pass")
        promote_acceptance(state, evidence, ledger=[evidence])
        self.assertEqual(state["acceptance"][0]["status"], "PASS")
        self.assertEqual(state["acceptance"][0]["evidence"], "ev-1")

    def test_cannot_promote_with_nonzero_exit_code(self):
        state = {
            "current_diff_hash": "abc",
            "acceptance": [
                {"id": "AC-1", "status": "FAIL", "statement": "does the thing"}
            ],
        }
        evidence = Evidence("ev-1", "vitest", 1, "abc", "base-1", "tests failed")
        state["evidence"] = [evidence]
        with self.assertRaises(ValueError):
            promote_acceptance(state, evidence)
        self.assertEqual(state["acceptance"][0]["status"], "FAIL")

    def test_tracking_required_without_issue_blocks_done(self):
        state = _ready_state(issue=None)
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("issue" in reason for reason in result.reasons))

    def test_quality_or_security_gate_not_pass_blocks_done(self):
        for field in ("quality_gate", "security_gate"):
            result = evaluate_completion(_ready_state(**{field: "FAIL"}))
            self.assertEqual(result.status, "FAIL")
            self.assertTrue(
                any(field.split("_")[0] in reason for reason in result.reasons)
            )

    def test_review_skip_requires_skip_reason(self):
        result = evaluate_completion(_ready_state(review_gate="SKIP"))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("review" in reason for reason in result.reasons))

    def test_justified_review_skip_can_be_ready(self):
        result = evaluate_completion(
            _ready_state(review_gate="SKIP", skip_reason="read-only inspect")
        )
        self.assertEqual(result.status, "READY_TO_SHIP")

    def test_mismatched_diff_hashes_block_done(self):
        result = evaluate_completion(_ready_state(verified_diff_hash="zzz"))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("diff_hash" in reason for reason in result.reasons))

    def test_ready_state_is_ready_to_ship(self):
        result = evaluate_completion(_ready_state())
        self.assertEqual(result.status, "READY_TO_SHIP")
        self.assertEqual(result.reasons, [])

    def test_required_approvals_are_loaded_from_completion_policy(self):
        result = evaluate_completion(_ready_state(approvals_required=["review"]))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("approval" in reason for reason in result.reasons))

    def test_explicitly_unrecorded_approvals_fail_closed(self):
        result = evaluate_completion(_ready_state(approvals_recorded=False))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("approval" in reason for reason in result.reasons))

    def test_recorded_required_approvals_allow_ready_to_ship(self):
        result = evaluate_completion(
            _ready_state(
                approvals_required=["review"],
                approvals_recorded=["review"],
            )
        )
        self.assertEqual(result.status, "READY_TO_SHIP")
        self.assertEqual(result.reasons, [])

    def test_promote_and_evaluate_accept_task_state(self):
        state = TaskState.new("task-1", "repo-1")
        state.tracking_required = True
        state.issue = 123
        state.current_diff_hash = "abc"
        state.acceptance = [
            AcceptanceCriterion(id="AC-1", statement="does the thing"),
        ]
        evidence = Evidence("ev-1", "vitest", 0, "abc", "base-1", "tests pass")
        state.evidence = [evidence]
        promote_acceptance(state, evidence)
        self.assertEqual(state.acceptance[0].status, "PASS")
        self.assertEqual(state.acceptance[0].evidence, "ev-1")

        state.quality_gate = _pass_report()
        state.security_gate = _pass_report()
        state.review_gate = "PASS"
        state.verified_diff_hash = "abc"
        state.reviewed_diff_hash = "abc"
        state.findings = []
        result = evaluate_completion(state)
        self.assertEqual(result.status, "READY_TO_SHIP")

    def test_stage_8_advances_only_when_ready_to_ship(self):
        state = TaskState.new("task-1", "repo-1")
        state.stage = 7
        state.tracking_required = True
        state.issue = 123
        state.current_diff_hash = "abc"
        state.acceptance = [
            AcceptanceCriterion(id="AC-1", statement="does the thing", status="FAIL"),
        ]
        with self.assertRaisesRegex(ValueError, "completion gate not satisfied"):
            advance_stage(state, 8)

        evidence = Evidence("ev-1", "vitest", 0, "abc", "base-1", "tests pass")
        state.evidence = [evidence]
        promote_acceptance(state, evidence)
        state.quality_gate = _pass_report()
        state.security_gate = _pass_report()
        state.review_gate = "PASS"
        state.verified_diff_hash = "abc"
        state.reviewed_diff_hash = "abc"
        state.findings = []
        advanced = advance_stage(state, 8)
        self.assertEqual(advanced.stage, 8)
        self.assertEqual(evaluate_completion(advanced).status, "READY_TO_SHIP")

    def test_completion_state_roundtrips_without_changing_result(self):
        import tempfile
        from pathlib import Path
        from nexus_harness.state import load_task_state, save_task_state

        state = TaskState.new("task-1", "repo-1")
        state.tracking_required = True
        state.issue = 123
        state.current_diff_hash = "abc"
        state.acceptance = [
            AcceptanceCriterion(
                id="AC-1", statement="does the thing", status="PASS", evidence="ev-1"
            )
        ]
        state.quality_gate = {"gate": "PASS", "diff_hash": "abc", "report": "q"}
        state.security_gate = {"gate": "PASS", "diff_hash": "abc", "report": "s"}
        state.review_gate = "SKIP"
        state.skip_reason = "not applicable"
        state.verified_diff_hash = "abc"
        state.reviewed_diff_hash = "abc"
        state.findings = [{"severity": "low", "status": "confirmed"}]
        state.evidence = [
            {"id": "ev-1", "exit_code": 0, "diff_hash": "abc", "base_commit": "base"}
        ]
        state.approvals_required = ["review"]
        state.approvals_recorded = ["review"]

        before = evaluate_completion(state)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            save_task_state(state, path)
            loaded = load_task_state(path)
        self.assertEqual(evaluate_completion(loaded), before)
        self.assertEqual(loaded.skip_reason, "not applicable")
        self.assertEqual(loaded.approvals_recorded, ["review"])

    def test_string_pass_quality_report_is_not_ready_to_ship(self):
        result = evaluate_completion(_ready_state(quality_gate="PASS"))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("quality" in reason for reason in result.reasons))

    def test_string_pass_security_report_is_not_ready_to_ship(self):
        result = evaluate_completion(_ready_state(security_gate="PASS"))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("security" in reason for reason in result.reasons))

    def test_empty_quality_diff_hash_blocks_ready_to_ship(self):
        result = evaluate_completion(
            _ready_state(quality_gate={"gate": "PASS", "diff_hash": ""})
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("quality" in reason and "fresh" in reason for reason in result.reasons)
        )

    def test_missing_quality_diff_hash_blocks_ready_to_ship(self):
        result = evaluate_completion(_ready_state(quality_gate={"gate": "PASS"}))
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("quality" in reason and "fresh" in reason for reason in result.reasons)
        )

    def test_diverging_security_diff_hash_blocks_ready_to_ship(self):
        result = evaluate_completion(
            _ready_state(security_gate={"gate": "PASS", "diff_hash": "zzz"})
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("security" in reason and "fresh" in reason for reason in result.reasons)
        )

    def test_quality_gate_fail_structured_report_blocks_ready_to_ship(self):
        result = evaluate_completion(
            _ready_state(quality_gate={"gate": "FAIL", "diff_hash": "abc"})
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("quality_gate" in reason for reason in result.reasons))

    def test_visual_required_fresh_desktop_and_mobile_is_ready(self):
        result = evaluate_completion(
            _ready_state(
                visual_required=True,
                visual_evidence=[_visual_ev("desktop"), _visual_ev("mobile")],
            )
        )
        self.assertEqual(result.status, "READY_TO_SHIP")
        self.assertEqual(result.reasons, [])

    def test_visual_required_stale_evidence_fails(self):
        result = evaluate_completion(
            _ready_state(
                visual_required=True,
                visual_evidence=[
                    _visual_ev("desktop", diff_hash="old"),
                    _visual_ev("mobile"),
                ],
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("visual evidence is not fresh" in reason for reason in result.reasons)
        )

    def test_visual_required_missing_mobile_fails(self):
        result = evaluate_completion(
            _ready_state(
                visual_required=True,
                visual_evidence=[_visual_ev("desktop")],
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("mobile" in reason for reason in result.reasons))

    def test_visual_required_console_policy_fail_blocks_ready(self):
        result = evaluate_completion(
            _ready_state(
                visual_required=True,
                visual_evidence=[
                    _visual_ev("desktop", console_error_count=1),
                    _visual_ev("mobile"),
                ],
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("console" in reason or "network" in reason for reason in result.reasons)
        )

    def test_matching_visual_paths_require_evidence(self):
        result = evaluate_completion(
            _ready_state(
                changed_paths=["apps/web/page.tsx"],
                visual_paths=["apps/web/**"],
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("desktop" in reason or "mobile" in reason for reason in result.reasons)
        )
