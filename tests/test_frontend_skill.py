import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills/nexus-frontend/SKILL.md"
ROUTER_PATH = ROOT / "skills/nexus-frontend/references/router.md"
HEURISTICS_PATH = ROOT / "docs/migration/unique-heuristics.md"
A11Y_REF_DIR = ROOT / "skills/accessibility/references"
A11Y_REFS = (
    "semantics-and-aria.md",
    "focus-and-keyboard.md",
    "forms.md",
    "hit-areas.md",
    "motion-and-zoom.md",
    "screen-readers.md",
)
AUTHORITY_ORDER = (
    "explicit user request",
    "project design system / brand",
    "explicit Figma or visual target",
    "surface specialist",
    "framework engineering guidance",
    "polish/generic guidance",
)
RETAINED_SPECIALISTS = (
    "design-motion-principles",
    "visual-validation",
    "Impeccable",
    "accessibility",
    "vercel-react-best-practices",
    "vercel-composition-patterns",
)
FRONTEND_HEURISTIC_SOURCES = (
    "ui-styling",
    "ui-ux-pro-max",
    "better-accessibility",
)


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

    def test_router_documents_authority_order(self):
        self.assertTrue(
            ROUTER_PATH.is_file(),
            msg="missing skills/nexus-frontend/references/router.md",
        )
        text = ROUTER_PATH.read_text(encoding="utf-8")
        for heading in AUTHORITY_ORDER:
            self.assertIn(heading, text)

    def test_router_names_retained_specialists(self):
        text = ROUTER_PATH.read_text(encoding="utf-8")
        for name in RETAINED_SPECIALISTS:
            self.assertIn(name, text)

    def test_router_forbids_multi_generic_load(self):
        text = ROUTER_PATH.read_text(encoding="utf-8")
        self.assertIn("Do not load multiple generic visual specialists", text)

    def test_accessibility_optional_references_exist(self):
        for name in A11Y_REFS:
            path = A11Y_REF_DIR / name
            self.assertTrue(path.is_file(), msg=f"missing {path.relative_to(ROOT)}")

    def test_frontend_heuristic_slice_is_evaluated(self):
        text = HEURISTICS_PATH.read_text(encoding="utf-8")
        for source in FRONTEND_HEURISTIC_SOURCES:
            self.assertIn(source, text)
            self.assertRegex(
                text,
                rf"{source}.*(?:PRESERVE|ALREADY COVERED|DISCARD)",
                msg=f"{source} row must record PRESERVE, ALREADY COVERED, or DISCARD",
            )
        self.assertNotRegex(
            text,
            r"(ui-styling|ui-ux-pro-max|better-accessibility)[^\n]*Pending extract",
            msg="frontend heuristic rows must not remain Pending extract",
        )
