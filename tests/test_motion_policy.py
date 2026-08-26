import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_TOML = ROOT / "core/quality/frontend.toml"
MOTION_POLICY = ROOT / "skills/nexus-frontend/references/motion-policy.md"
SKILL_PATH = ROOT / "skills/nexus-frontend/SKILL.md"
VENDOR_LOCK = ROOT / "upstream/vendor-lock.json"
RUNTIME_SKILLS = ROOT / "skills"
UPSTREAM_MOTION = "upstream/design-motion-principles"
VENDOR_LOCK_REL = "upstream/vendor-lock.json"

MOTION_FLAGS = {
    "required": False,
    "ask_before_animating": True,
    "prefers_reduced_motion": True,
    "avoid_hover_scale_everywhere": True,
    "avoid_decorative_stagger": True,
    "avoid_bounce_for_productivity": True,
    "avoid_layout_shift": True,
    "must_not_block_interaction": True,
}
ASYNC_FLAGS = {
    "review_loading": True,
    "review_empty": True,
    "review_error": True,
    "review_disabled": True,
    "review_transition": True,
}
SKELETON_FLAGS = {
    "only_when_wait_meaningful": True,
    "only_when_shape_predictable": True,
}


class MotionPolicyTests(unittest.TestCase):
    def _require_policy_files(self) -> None:
        self.assertTrue(
            FRONTEND_TOML.is_file(),
            msg="missing core/quality/frontend.toml",
        )
        self.assertTrue(
            MOTION_POLICY.is_file(),
            msg="missing skills/nexus-frontend/references/motion-policy.md",
        )

    def test_policy_files_exist(self):
        self._require_policy_files()

    def test_frontend_toml_machine_readable_flags(self):
        self._require_policy_files()
        with FRONTEND_TOML.open("rb") as handle:
            policy = tomllib.load(handle)

        self.assertEqual(policy["motion"], MOTION_FLAGS)
        self.assertEqual(policy["async"], ASYNC_FLAGS)
        self.assertEqual(policy["skeleton"], SKELETON_FLAGS)
        self.assertTrue(policy["progress"]["only_when_measurable"])
        self.assertTrue(policy["optimistic"]["only_when_rollback_safe"])
        self.assertTrue(policy["lazy"]["non_critical_routes_components_media"])

        raw = FRONTEND_TOML.read_text(encoding="utf-8")
        self.assertNotIn("sdr", raw.lower())

    def test_human_policy_contains_required_rules(self):
        self._require_policy_files()
        text = MOTION_POLICY.read_text(encoding="utf-8")

        self.assertIn("prefers-reduced-motion", text)
        self.assertIn("not skeleton-everywhere", text)
        self.assertIn("lazy loading for non-critical resources", text)
        for state in ("loading", "empty", "error", "disabled", "transition"):
            self.assertIn(state, text)
        self.assertIn("Do not animate every element by default", text)
        self.assertIn("should this animate at all?", text)
        self.assertIn("progress only when measurable", text)
        self.assertIn("optimistic UI only when rollback is safe", text)
        self.assertIn("hover scale everywhere", text)
        self.assertIn("decorative stagger", text)
        self.assertIn("bounce/spring for routine productivity UI", text)
        self.assertIn("layout shift", text)
        self.assertIn("animation blocking interaction", text)
        self.assertIn(UPSTREAM_MOTION, text)
        self.assertIn(VENDOR_LOCK_REL, text)
        self.assertNotIn("The Three Designers", text)

    def test_skill_routes_motion_to_locked_upstream(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("references/motion-policy.md", text)
        self.assertIn(UPSTREAM_MOTION, text)
        self.assertIn(VENDOR_LOCK_REL, text)
        for mode in (
            "implement",
            "redesign",
            "audit",
            "explain",
            "visual-validate",
            "design-system",
            "polish",
        ):
            self.assertIn(f"`{mode}`", text)

    def test_motion_source_is_vendor_locked_not_copied(self):
        with VENDOR_LOCK.open(encoding="utf-8") as handle:
            lock = json.load(handle)
        source = next(
            item for item in lock["sources"] if item["id"] == "design-motion-principles"
        )
        self.assertEqual(source["canonical_path"], UPSTREAM_MOTION)
        self.assertTrue(
            (ROOT / UPSTREAM_MOTION).exists(),
            msg="locked motion source missing on disk",
        )
        self.assertFalse(
            (RUNTIME_SKILLS / "design-motion-principles").exists(),
            msg="do not vendor a second unversioned copy into runtime roots",
        )
        self.assertFalse(
            (RUNTIME_SKILLS / "design-motion-principles" / "SKILL.md").is_file()
        )
