"""Hermetic proof that visual PASS is bound to the verified frontend diff.

No client repo edits, no browser download, no network. Reuses
evaluate_completion + VisualEvidence + evaluate_visual_gate.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nexus_harness.affected import load_ci_profile
from nexus_harness.completion import evaluate_completion
from nexus_harness.evidence import read_evidence
from nexus_harness.frontend_review import (
    apply_reviewer_status,
    evaluate_visual_gate,
    normalize_reviewer_response,
)
from nexus_harness.playwright import capture_route
from nexus_harness.state import TaskState
from nexus_harness.visual import (
    VisualEvidence,
    confine_visual_artifacts,
    is_valid_visual_skip,
    is_visual_required,
    runtime_policy_ok,
)


ROOT = Path(__file__).resolve().parents[1]
SDR_PROFILE = ROOT / "profiles" / "projects" / "sdr-platform.toml"


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
        "changed_paths": ["apps/web/page.tsx"],
        "visual_paths": ["apps/web/**"],
    }
    state.update(overrides)
    return state


def _rebind_non_visual_hashes(state, diff_hash):
    """Update quality/security/review/acceptance hashes; leave visual evidence."""
    state["current_diff_hash"] = diff_hash
    state["verified_diff_hash"] = diff_hash
    state["reviewed_diff_hash"] = diff_hash
    state["quality_gate"] = _pass_report(diff_hash)
    state["security_gate"] = _pass_report(diff_hash)
    state["evidence"] = [
        {**record, "diff_hash": diff_hash} for record in state["evidence"]
    ]
    return state


def _passing_review(screenshot="mobile-after.png"):
    findings = normalize_reviewer_response(
        {
            "findings": [
                {
                    "severity": "high",
                    "confirmed": False,
                    "status": "suspected",
                    "category": "layout",
                    "description": "Possible clip at 390px",
                    "route": "/",
                    "viewport": "mobile",
                    "screenshot": screenshot,
                    "evidence": screenshot,
                    "confidence": 0.41,
                }
            ]
        }
    )
    return findings, evaluate_visual_gate(findings)


def _blocking_review(screenshot="mobile-after.png"):
    findings = normalize_reviewer_response(
        {
            "findings": [
                {
                    "severity": "high",
                    "confirmed": True,
                    "status": "confirmed",
                    "category": "layout",
                    "description": "Primary CTA is clipped at 390px",
                    "route": "/",
                    "viewport": "mobile",
                    "screenshot": screenshot,
                    "evidence": screenshot,
                    "confidence": 0.91,
                }
            ]
        }
    )
    return findings, evaluate_visual_gate(findings)


def _record_viewports(root: Path, diff_hash: str, reviewer_status: str):
    recorded = []
    for viewport in ("desktop", "mobile"):
        names = {
            "screenshot": f"{viewport}-after.png",
            "baseline": f"{viewport}-before.png",
            "trace": f"{viewport}.zip",
        }
        for name in names.values():
            (root / name).write_bytes(b"fixture")
        evidence = VisualEvidence(
            route="/",
            viewport=viewport,
            diff_hash=diff_hash,
            screenshot=names["screenshot"],
            baseline=names["baseline"],
            trace=names["trace"],
            console_error_count=0,
            failed_request_count=0,
        )
        confined = confine_visual_artifacts(evidence, root)
        recorded.append(apply_reviewer_status(confined, reviewer_status))
    return recorded


class FrontendIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.profile = load_ci_profile(SDR_PROFILE)
        self.assertIsNotNone(self.profile.frontend)
        self.visual_paths = list(self.profile.frontend.visual_paths)

    def tearDown(self):
        self._tmp.cleanup()

    def _capture_with_mock_runner(self, diff_hash: str):
        task = TaskState.new("task-7", "sdr-platform")
        task.current_diff_hash = diff_hash
        seen: list[list[str]] = []

        def runner(argv, *, cwd=None):
            seen.append(list(argv))
            return 0, "", ""

        result = capture_route(
            "/",
            config=self.profile.frontend,
            artifact_root=self.root,
            runner=runner,
            task_id="task-7",
            task_state=task,
        )
        self.assertTrue(result.ok)
        self.assertEqual(len(seen), 1)
        joined = " ".join(seen[0])
        self.assertNotIn("playwright install", joined)
        self.assertNotIn("https://", joined)
        records = read_evidence(result.evidence_path)
        self.assertEqual(records[0].diff_hash, diff_hash)
        self.assertEqual(records[0].exit_code, 0)
        return result

    def test_visual_pass_is_bound_to_verified_diff(self):
        self.assertEqual(self.visual_paths, ["apps/web/**"])
        self._capture_with_mock_runner("abc")

        findings, review_status = _passing_review()
        self.assertEqual(review_status, "PASS")
        evidence = _record_viewports(self.root, "abc", review_status)
        self.assertEqual(len(evidence), 2)
        for item in evidence:
            self.assertTrue(item.is_fresh("abc"))
            self.assertTrue(item.screenshot)
            self.assertTrue(runtime_policy_ok(item))
            self.assertEqual(item.reviewer_status, "PASS")

        state = _ready_state(
            changed_paths=["apps/web/page.tsx"],
            visual_paths=self.visual_paths,
            visual_evidence=evidence,
            findings=[item.to_dict() for item in findings],
        )
        self.assertTrue(is_visual_required(state))

        phase_a = evaluate_completion(state)
        self.assertEqual(phase_a.status, "READY_TO_SHIP")
        self.assertEqual(phase_a.reasons, [])

        _rebind_non_visual_hashes(state, "def")
        phase_b = evaluate_completion(state)
        self.assertEqual(phase_b.status, "FAIL")
        self.assertTrue(
            any("visual evidence is not fresh" in reason for reason in phase_b.reasons),
            msg=phase_b.reasons,
        )
        self.assertFalse(
            any("quality report is not fresh" in reason for reason in phase_b.reasons)
        )
        self.assertFalse(
            any("security report is not fresh" in reason for reason in phase_b.reasons)
        )
        self.assertFalse(
            any(
                "acceptance evidence is not fresh" in reason
                for reason in phase_b.reasons
            )
        )

        fresh_findings, fresh_status = _passing_review()
        self.assertEqual(fresh_status, "PASS")
        state["visual_evidence"] = _record_viewports(self.root, "def", fresh_status)
        state["findings"] = [item.to_dict() for item in fresh_findings]
        phase_c = evaluate_completion(state)
        self.assertEqual(phase_c.status, "READY_TO_SHIP")
        self.assertEqual(phase_c.reasons, [])

    def test_invalid_non_visual_skip_does_not_restore_ready(self):
        findings, review_status = _passing_review()
        state = _ready_state(
            visual_paths=self.visual_paths,
            visual_evidence=_record_viewports(self.root, "abc", review_status),
            findings=[item.to_dict() for item in findings],
        )
        _rebind_non_visual_hashes(state, "def")
        state["visual_skip"] = {
            "kind": "non_visual",
            "reason": "looks fine, no need to recapture",
        }
        self.assertFalse(is_valid_visual_skip(state["visual_skip"]))
        self.assertTrue(is_visual_required(state))
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("visual evidence is not fresh" in reason for reason in result.reasons),
            msg=result.reasons,
        )

    def test_confirmed_high_visual_finding_blocks_fresh_screenshots(self):
        findings, review_status = _blocking_review()
        self.assertEqual(review_status, "FAIL")
        evidence = _record_viewports(self.root, "def", review_status)
        for item in evidence:
            self.assertTrue(item.is_fresh("def"))
            self.assertTrue(item.screenshot)
            self.assertTrue(runtime_policy_ok(item))
            self.assertEqual(item.reviewer_status, "FAIL")

        state = _ready_state(
            current_diff_hash="def",
            verified_diff_hash="def",
            reviewed_diff_hash="def",
            quality_gate=_pass_report("def"),
            security_gate=_pass_report("def"),
            evidence=[{"id": "ev-1", "exit_code": 0, "diff_hash": "def"}],
            visual_paths=self.visual_paths,
            visual_evidence=evidence,
            findings=[item.to_dict() for item in findings],
        )
        self.assertTrue(is_visual_required(state))
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("finding" in reason or "high" in reason for reason in result.reasons),
            msg=result.reasons,
        )
        self.assertFalse(
            any("visual evidence is not fresh" in reason for reason in result.reasons)
        )


if __name__ == "__main__":
    unittest.main()
