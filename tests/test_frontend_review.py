import unittest
from pathlib import Path

from nexus_harness.completion import evaluate_completion
from nexus_harness.frontend_review import (
    FINDING_CATEGORIES,
    UnknownCategoryError,
    apply_reviewer_status,
    evaluate_visual_gate,
    normalize_finding,
    normalize_reviewer_response,
)
from nexus_harness.visual import VisualEvidence, visual_completion_reasons


ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agents/frontend-visual-reviewer.md"

CATEGORIES = (
    "layout",
    "responsive",
    "state",
    "motion",
    "accessibility",
    "design-system",
)


def _reviewer_finding(**overrides):
    payload = {
        "severity": "high",
        "confirmed": True,
        "confidence": 0.86,
        "route": "/inbox",
        "viewport": "mobile",
        "screenshot": "inbox-mobile.png",
        "category": "layout",
        "description": "Primary CTA is clipped at 390px",
        "evidence": "inbox-mobile.png right edge",
    }
    payload.update(overrides)
    return payload


def _ready_state(**overrides):
    state = {
        "tracking_required": True,
        "issue": 123,
        "acceptance": [{"id": "AC-1", "status": "PASS", "evidence": "ev-1"}],
        "quality_gate": {"gate": "PASS", "diff_hash": "abc", "report": "structured"},
        "security_gate": {"gate": "PASS", "diff_hash": "abc", "report": "structured"},
        "review_gate": "PASS",
        "current_diff_hash": "abc",
        "verified_diff_hash": "abc",
        "reviewed_diff_hash": "abc",
        "evidence": [{"id": "ev-1", "exit_code": 0, "diff_hash": "abc"}],
        "findings": [],
    }
    state.update(overrides)
    return state


class NormalizeReviewTests(unittest.TestCase):
    def test_normalizes_severity_confidence_screenshot_route_and_category(self):
        finding = normalize_finding(_reviewer_finding())
        self.assertEqual(finding.severity, "high")
        self.assertEqual(finding.confidence, 0.86)
        self.assertEqual(finding.route, "/inbox")
        self.assertEqual(finding.viewport, "mobile")
        self.assertEqual(finding.screenshot, "inbox-mobile.png")
        self.assertEqual(finding.category, "layout")
        self.assertEqual(finding.description, "Primary CTA is clipped at 390px")
        self.assertEqual(finding.evidence, "inbox-mobile.png right edge")
        self.assertTrue(finding.confirmed)

    def test_status_confirmed_is_treated_as_confirmed(self):
        finding = normalize_finding(
            _reviewer_finding(confirmed=False, status="confirmed")
        )
        self.assertTrue(finding.confirmed)
        self.assertEqual(finding.status, "confirmed")

    def test_normalizes_reviewer_response_list(self):
        findings = normalize_reviewer_response(
            {
                "findings": [
                    _reviewer_finding(category=category) for category in CATEGORIES
                ]
            }
        )
        self.assertEqual(len(findings), len(CATEGORIES))
        self.assertEqual(
            [item.category for item in findings],
            list(CATEGORIES),
        )
        self.assertEqual(FINDING_CATEGORIES, frozenset(CATEGORIES))

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(UnknownCategoryError):
            normalize_finding(_reviewer_finding(category="typography"))


class VisualGateTests(unittest.TestCase):
    def test_confirmed_high_finding_blocks_visual_gate(self):
        findings = normalize_reviewer_response({"findings": [_reviewer_finding()]})
        self.assertEqual(evaluate_visual_gate(findings), "FAIL")

    def test_medium_and_low_do_not_block_visual_gate(self):
        findings = normalize_reviewer_response(
            {
                "findings": [
                    _reviewer_finding(
                        severity="medium",
                        category="state",
                        description="Empty state copy is weak",
                    ),
                    _reviewer_finding(
                        severity="low",
                        category="design-system",
                        description="Token spacing is one step off",
                    ),
                ]
            }
        )
        self.assertEqual(evaluate_visual_gate(findings), "PASS")
        self.assertEqual(len(findings), 2)

    def test_unconfirmed_high_does_not_block_visual_gate(self):
        findings = normalize_reviewer_response(
            {
                "findings": [
                    _reviewer_finding(confirmed=False, status="suspected"),
                ]
            }
        )
        self.assertEqual(evaluate_visual_gate(findings), "PASS")

    def test_attached_confirmed_high_fails_completion_via_plan2(self):
        findings = normalize_reviewer_response({"findings": [_reviewer_finding()]})
        result = evaluate_completion(
            _ready_state(findings=[item.to_dict() for item in findings])
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("finding" in reason or "high" in reason for reason in result.reasons)
        )

    def test_attached_medium_does_not_fail_completion(self):
        findings = normalize_reviewer_response(
            {
                "findings": [
                    _reviewer_finding(
                        severity="medium",
                        category="responsive",
                        description="Secondary nav wraps early",
                    )
                ]
            }
        )
        result = evaluate_completion(
            _ready_state(findings=[item.to_dict() for item in findings])
        )
        self.assertEqual(result.status, "READY_TO_SHIP")

    def test_reviewer_status_is_set_from_visual_gate(self):
        findings = normalize_reviewer_response({"findings": [_reviewer_finding()]})
        evidence = VisualEvidence(
            route="/inbox",
            viewport="mobile",
            diff_hash="abc",
            screenshot="inbox-mobile.png",
        )
        updated = apply_reviewer_status(evidence, evaluate_visual_gate(findings))
        self.assertEqual(updated.reviewer_status, "FAIL")
        self.assertEqual(updated.diff_hash, "abc")

    def test_visual_gate_fail_does_not_satisfy_visual_completion(self):
        findings = normalize_reviewer_response({"findings": [_reviewer_finding()]})
        status = evaluate_visual_gate(findings)
        evidence = [
            apply_reviewer_status(
                VisualEvidence(
                    route="/inbox",
                    viewport=viewport,
                    diff_hash="abc",
                    screenshot=f"{viewport}.png",
                    baseline=f"{viewport}-before.png",
                ),
                status,
            )
            for viewport in ("desktop", "mobile")
        ]
        reasons = visual_completion_reasons(
            {"visual_required": True, "visual_evidence": evidence},
            "abc",
        )
        self.assertTrue(
            any("visual review is not PASS" in reason for reason in reasons)
        )


class ReviewerAgentTests(unittest.TestCase):
    def test_agent_forbids_implementer_chat_history_as_evidence(self):
        self.assertTrue(
            AGENT_PATH.is_file(),
            msg="missing agents/frontend-visual-reviewer.md",
        )
        text = AGENT_PATH.read_text(encoding="utf-8")
        lowered = text.lower()
        self.assertIn("not the implementer's full conversational history", lowered)
        self.assertIn("do not use implementer chat history as evidence", lowered)
        self.assertIn("acceptance criteria", lowered)
        self.assertIn("design system", lowered)
        self.assertIn("screenshot", lowered)
        self.assertIn("viewport", lowered)
        self.assertIn("console", lowered)
        self.assertIn("network", lowered)

    def test_agent_routes_accessibility_and_motion_without_second_saas(self):
        text = AGENT_PATH.read_text(encoding="utf-8")
        self.assertIn("skills/accessibility", text)
        self.assertIn("prefers-reduced-motion", text)
        self.assertIn("keyboard", text)
        self.assertIn("focus", text)
        self.assertIn("contrast", text)
        self.assertIn("loading", text)
        self.assertIn("error", text)
        self.assertIn("skills/nexus-frontend/references/motion-policy.md", text)
        self.assertIn("upstream/design-motion-principles", text)
        self.assertIn("Do not paste", text)
        self.assertIn("Do not add a second accessibility", text)
        for category in CATEGORIES:
            self.assertIn(category, text)
        self.assertNotIn("The Three Designers", text)
