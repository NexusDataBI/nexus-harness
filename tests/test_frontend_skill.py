import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills/nexus-frontend/SKILL.md"


class FrontendSkillContractTests(unittest.TestCase):
    def test_uses_canonical_routing_names(self):
        content = SKILL_PATH.read_text(encoding="utf-8")

        for legacy_name in (
            "interface-review",
            "explain-interface",
            "web-design-guidelines",
            "design-taste-frontend",
        ):
            self.assertNotIn(legacy_name, content)

        for mode in (
            "implement",
            "redesign",
            "audit",
            "explain",
            "visual-validate",
            "design-system",
            "polish",
        ):
            self.assertIn(f"`{mode}`", content)
