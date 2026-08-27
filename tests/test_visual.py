import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from nexus_harness.devserver import parse_frontend_section
from nexus_harness.safe import PathSafetyError
from nexus_harness.state import TaskState
from nexus_harness.visual import (
    VisualEvidence,
    bind_visual_requirement,
    confine_visual_artifacts,
    is_valid_visual_skip,
    is_visual_required,
    visual_completion_reasons,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "core/quality/visual-evidence.schema.json"
FRONTEND_TOML = ROOT / "core/quality/frontend.toml"
COMPLETION_TOML = ROOT / "core/workflow/completion.toml"


def _bundle(
    viewport: str,
    *,
    diff_hash: str = "abc",
    screenshot: str | None = "after.png",
    **overrides,
) -> dict:
    payload = {
        "route": "/",
        "viewport": viewport,
        "diff_hash": diff_hash,
        "screenshot": screenshot,
        "baseline": "before.png",
        "trace": "trace.zip",
        "console_error_count": 0,
        "failed_request_count": 0,
        "reviewer_status": "PASS",
        "base_commit": "base",
    }
    payload.update(overrides)
    return payload


class VisualEvidenceTests(unittest.TestCase):
    def test_visual_evidence_is_stale_after_ui_diff_changes(self):
        ev = VisualEvidence(
            route="/", viewport="desktop", diff_hash="abc", screenshot="after.png"
        )
        self.assertFalse(ev.is_fresh("def"))

    def test_visual_evidence_is_fresh_for_matching_diff(self):
        ev = VisualEvidence(
            route="/", viewport="desktop", diff_hash="abc", screenshot="after.png"
        )
        self.assertTrue(ev.is_fresh("abc"))

    def test_freshness_is_diff_hash_equality_only(self):
        ev = VisualEvidence(
            route="/inbox",
            viewport="mobile",
            diff_hash="abc",
            screenshot="after.png",
            console_error_count=3,
        )
        self.assertTrue(ev.is_fresh("abc"))
        self.assertFalse(ev.is_fresh("other"))

    def test_default_limitation_warns_about_runtime_secrets(self):
        ev = VisualEvidence(
            route="/", viewport="desktop", diff_hash="abc", screenshot="after.png"
        )
        text = (ev.limitation or "").lower()
        self.assertIn("token", text)
        self.assertIn("cookie", text)
        self.assertIn("authorization", text)


class VisualRequirementTests(unittest.TestCase):
    def test_matching_visual_path_requires_desktop_and_mobile(self):
        state = {
            "current_diff_hash": "abc",
            "changed_paths": ["apps/web/src/page.tsx"],
            "visual_paths": ["apps/web/**"],
            "visual_evidence": [_bundle("desktop")],
        }
        self.assertTrue(is_visual_required(state))
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(any("mobile" in reason for reason in reasons))

    def test_unrelated_path_does_not_require_visual(self):
        state = {
            "changed_paths": ["apps/server/main.py"],
            "visual_paths": ["apps/web/**"],
        }
        self.assertFalse(is_visual_required(state))
        self.assertEqual(visual_completion_reasons(state, "abc"), [])

    def test_explicit_visual_required_needs_both_viewports(self):
        state = {
            "visual_required": True,
            "visual_evidence": [_bundle("desktop"), _bundle("mobile")],
        }
        self.assertTrue(is_visual_required(state))
        self.assertEqual(visual_completion_reasons(state, "abc"), [])

    def test_explicit_visual_required_cannot_drop_a_viewport(self):
        state = {
            "visual_required": True,
            "visual_evidence": [_bundle("desktop")],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(any("mobile" in reason for reason in reasons))

    def test_reads_visual_paths_from_frontend_when_state_list_empty(self):
        state = {
            "changed_paths": ["apps/web/page.tsx"],
            "frontend": {"visual_paths": ["apps/web/**"]},
        }
        self.assertTrue(is_visual_required(state))
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(
            any("desktop" in reason or "mobile" in reason for reason in reasons)
        )

    def test_bind_visual_requirement_copies_profile_paths(self):
        parsed = parse_frontend_section(
            {
                "base_url": "http://127.0.0.1:3000",
                "readiness_url": "http://127.0.0.1:3000",
                "visual_paths": ["apps/web/**"],
                "dev_server": {"command": ["npm", "run", "dev"], "timeout_seconds": 2},
            }
        )
        self.assertTrue(parsed.ok)
        profile = type("Profile", (), {"frontend": parsed.config})()
        state = TaskState.new("task-bind", "demo")
        bind_visual_requirement(state, profile, ["apps/web/page.tsx"])
        self.assertEqual(list(state.visual_paths), ["apps/web/**"])
        self.assertEqual(list(state.changed_paths), ["apps/web/page.tsx"])


class VisualSkipTests(unittest.TestCase):
    def test_structured_non_visual_skip_bypasses_requirement(self):
        for kind in ("type_only", "test_only", "no_render"):
            state = {
                "changed_paths": ["apps/web/src/page.tsx"],
                "visual_paths": ["apps/web/**"],
                "visual_skip": {
                    "kind": kind,
                    "reason": f"{kind} change with no rendered effect",
                },
            }
            self.assertFalse(is_visual_required(state), msg=kind)
            self.assertTrue(is_valid_visual_skip(state["visual_skip"]))
            self.assertEqual(visual_completion_reasons(state, "abc"), [])

    def test_empty_reason_does_not_bypass(self):
        skip = {"kind": "type_only", "reason": "   "}
        self.assertFalse(is_valid_visual_skip(skip))
        state = {
            "changed_paths": ["apps/web/page.tsx"],
            "visual_paths": ["apps/web/**"],
            "visual_skip": skip,
        }
        self.assertTrue(is_visual_required(state))

    def test_generic_skip_string_does_not_bypass(self):
        self.assertFalse(is_valid_visual_skip("skip"))
        state = {
            "visual_required": True,
            "visual_skip": "skip",
        }
        self.assertTrue(is_visual_required(state))

    def test_unknown_kind_does_not_bypass(self):
        skip = {"kind": "looks_fine", "reason": "trust me"}
        self.assertFalse(is_valid_visual_skip(skip))
        state = {
            "changed_paths": ["apps/web/page.tsx"],
            "visual_paths": ["apps/web/**"],
            "visual_skip": skip,
        }
        self.assertTrue(is_visual_required(state))


class VisualBundleTests(unittest.TestCase):
    def test_new_route_may_omit_baseline_with_reason(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle(
                    "desktop",
                    baseline=None,
                    baseline_missing_reason="new route /onboarding",
                ),
                _bundle(
                    "mobile",
                    baseline=None,
                    baseline_missing_reason="new route /onboarding",
                ),
            ],
        }
        self.assertEqual(visual_completion_reasons(state, "abc"), [])

    def test_missing_baseline_without_reason_fails_bundle(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle("desktop", baseline=None, baseline_missing_reason=""),
                _bundle("mobile"),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(any("baseline" in reason for reason in reasons))

    def test_stale_viewport_is_not_fresh(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle("desktop", diff_hash="old"),
                _bundle("mobile"),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(
            any("visual evidence is not fresh" in reason for reason in reasons)
        )

    def test_unallowlisted_console_error_fails_bundle(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle(
                    "desktop",
                    console_error_count=1,
                    console_messages=["TypeError: Cannot read properties of undefined"],
                ),
                _bundle("mobile"),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(
            any("console" in reason or "network" in reason for reason in reasons)
        )

    def test_allowlisted_console_noise_does_not_fail(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle(
                    "desktop",
                    console_error_count=1,
                    console_messages=["Download the React DevTools"],
                ),
                _bundle("mobile"),
            ],
        }
        self.assertEqual(visual_completion_reasons(state, "abc"), [])

    def test_unallowlisted_failed_request_fails_bundle(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle(
                    "desktop",
                    failed_request_count=1,
                    failed_request_urls=["https://api.example.test/leads"],
                ),
                _bundle("mobile"),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(
            any("network" in reason or "console" in reason for reason in reasons)
        )

    def test_console_error_count_without_allowlist_match_fails(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle("desktop", console_error_count=2),
                _bundle("mobile"),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(
            any("console" in reason or "network" in reason for reason in reasons)
        )

    def test_screenshot_outside_evidence_root_is_rejected(self):
        ev = VisualEvidence(
            route="/",
            viewport="desktop",
            diff_hash="abc",
            screenshot="/tmp/escape.png",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            root.mkdir()
            with self.assertRaises(PathSafetyError):
                confine_visual_artifacts(ev, root)

    def test_relative_screenshot_under_evidence_root_is_confined(self):
        ev = VisualEvidence(
            route="/",
            viewport="desktop",
            diff_hash="abc",
            screenshot="after.png",
            baseline="before.png",
            trace="trace.zip",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            root.mkdir()
            confined = confine_visual_artifacts(ev, root)
            expected_root = root.resolve()
            for field in (confined.screenshot, confined.baseline, confined.trace):
                resolved = Path(field)
                self.assertTrue(resolved.is_absolute())
                self.assertTrue(resolved.is_relative_to(expected_root))
            self.assertEqual(Path(confined.screenshot), expected_root / "after.png")

    def test_relative_escape_screenshot_is_rejected(self):
        ev = VisualEvidence(
            route="/",
            viewport="desktop",
            diff_hash="abc",
            screenshot="../escape.png",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            root.mkdir()
            with self.assertRaises(PathSafetyError):
                confine_visual_artifacts(ev, root)


class VisualReviewRequiredTests(unittest.TestCase):
    def test_fresh_desktop_and_mobile_with_reviewer_pass_are_ready(self):
        state = {
            "visual_required": True,
            "visual_evidence": [_bundle("desktop"), _bundle("mobile")],
        }
        self.assertEqual(visual_completion_reasons(state, "abc"), [])

    def test_missing_reviewer_status_fails_visual_completion(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle("desktop", reviewer_status=None),
                _bundle("mobile", reviewer_status=""),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(
            any("visual review is not PASS" in reason for reason in reasons)
        )

    def test_reviewer_status_fail_fails_visual_completion(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle("desktop", reviewer_status="FAIL"),
                _bundle("mobile", reviewer_status="FAIL"),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(
            any("visual review is not PASS" in reason for reason in reasons)
        )

    def test_unknown_reviewer_status_fails_visual_completion(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle("desktop", reviewer_status="PENDING"),
                _bundle("mobile", reviewer_status="ok"),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(
            any("visual review is not PASS" in reason for reason in reasons)
        )

    def test_desktop_pass_mobile_missing_reviewer_fails(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle("desktop", reviewer_status="PASS"),
                _bundle("mobile", reviewer_status=None),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(any("mobile" in reason for reason in reasons))
        self.assertTrue(
            any("visual review is not PASS" in reason for reason in reasons)
        )

    def test_reviewer_pass_does_not_rescue_stale_diff(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle("desktop", reviewer_status="PASS"),
                _bundle("mobile", reviewer_status="PASS"),
            ],
        }
        reasons = visual_completion_reasons(state, "def")
        self.assertTrue(
            any("visual evidence is not fresh" in reason for reason in reasons)
        )

    def test_generic_review_gate_does_not_substitute_visual_review(self):
        state = {
            "visual_required": True,
            "review_gate": "PASS",
            "visual_evidence": [
                _bundle("desktop", reviewer_status=None),
                _bundle("mobile", reviewer_status=None),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(
            any("visual review is not PASS" in reason for reason in reasons)
        )


class VisualAttemptHistoryTests(unittest.TestCase):
    def test_newest_failed_attempt_wins_over_older_pass(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle(
                    "desktop",
                    attempt_ok=True,
                    captured_at="2026-08-27T10:00:00+00:00",
                ),
                _bundle(
                    "mobile",
                    attempt_ok=True,
                    captured_at="2026-08-27T10:00:00+00:00",
                ),
                _bundle(
                    "desktop",
                    screenshot=None,
                    reviewer_status="FAIL",
                    attempt_ok=False,
                    captured_at="2026-08-27T11:00:00+00:00",
                ),
                _bundle(
                    "mobile",
                    screenshot=None,
                    reviewer_status="FAIL",
                    attempt_ok=False,
                    captured_at="2026-08-27T11:00:00+00:00",
                ),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(reasons)
        self.assertTrue(any("recapture failed" in reason for reason in reasons))

    def test_later_index_failed_attempt_wins_without_timestamp(self):
        state = {
            "visual_required": True,
            "visual_evidence": [
                _bundle("desktop"),
                _bundle("mobile"),
                _bundle(
                    "desktop",
                    screenshot=None,
                    reviewer_status="FAIL",
                    attempt_ok=False,
                ),
                _bundle(
                    "mobile",
                    screenshot=None,
                    reviewer_status="FAIL",
                    attempt_ok=False,
                ),
            ],
        }
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(reasons)


class VisualContractTests(unittest.TestCase):
    def test_schema_requires_route_viewport_diff_hash(self):
        self.assertTrue(SCHEMA.is_file())
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(set(schema["required"]), {"route", "viewport", "diff_hash"})
        self.assertFalse(schema["additionalProperties"])
        for field in (
            "screenshot",
            "baseline",
            "baseline_missing_reason",
            "trace",
            "console_error_count",
            "failed_request_count",
            "reviewer_status",
            "limitation",
            "attempt_ok",
            "captured_at",
        ):
            self.assertIn(field, schema["properties"])

    def test_frontend_toml_defines_console_network_allowlist(self):
        with FRONTEND_TOML.open("rb") as handle:
            policy = tomllib.load(handle)
        visual = policy["visual"]
        self.assertEqual(list(visual["required_viewports"]), ["desktop", "mobile"])
        self.assertIn("Download the React DevTools", visual["console"]["allowlist"])
        self.assertTrue(visual["network"]["allowlist"])

    def test_completion_policy_documents_visual_when_required(self):
        with COMPLETION_TOML.open("rb") as handle:
            policy = tomllib.load(handle)
        self.assertTrue(policy["require"]["visual_evidence_fresh_when_required"])
        self.assertTrue(policy["require"]["visual_review_pass_when_required"])


if __name__ == "__main__":
    unittest.main()
