import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills/nexus-frontend/SKILL.md"
ROUTER_PATH = ROOT / "skills/nexus-frontend/references/router.md"
DESIGN_READ_PATH = ROOT / "skills/nexus-frontend/references/design-read.md"
SURFACE_INTENT_PATH = ROOT / "skills/nexus-frontend/references/surface-intent.md"
DIRECTION_PATH = ROOT / "skills/nexus-frontend/references/design-direction.md"
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
    "approved Design Read / surface contract",
    "surface specialist",
    "framework engineering guidance",
    "generic/search intelligence and polish",
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
            "code-to-figma",
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

    def test_surface_contract_has_intent_and_type_axes(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        for intent in ("persuade", "operate", "read", "experience"):
            self.assertIn(intent, text)
        for surface in ("marketing", "product", "data-dense", "motion", "figma"):
            self.assertIn(surface, text)
        self.assertIn("intent:", text)
        self.assertIn("surface:", text)

    def test_design_read_contract_is_explicit(self):
        self.assertTrue(DESIGN_READ_PATH.is_file())
        text = DESIGN_READ_PATH.read_text(encoding="utf-8")
        for field in (
            "subject:",
            "audience:",
            "primary_job:",
            "authority:",
            "memorable_move:",
            "variance:",
            "motion:",
            "density:",
            "avoid:",
        ):
            self.assertIn(field, text)
        self.assertIn("unrelated product", text)

    def test_design_direction_rejects_default_substitution(self):
        self.assertTrue(DIRECTION_PATH.is_file())
        text = DIRECTION_PATH.read_text(encoding="utf-8")
        self.assertIn("new house style", text)
        skill = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "Never replace one default aesthetic with another default aesthetic",
            skill,
        )

    def test_surface_intent_reference_exists(self):
        self.assertTrue(SURFACE_INTENT_PATH.is_file())
        text = SURFACE_INTENT_PATH.read_text(encoding="utf-8")
        self.assertIn("Classify the route/surface", text)
        self.assertIn("Intent sets the experience priority", text)

    def test_generic_intelligence_is_advisory_only(self):
        text = ROUTER_PATH.read_text(encoding="utf-8")
        self.assertIn("ui-ux-pro-max", text)
        self.assertIn("advisory only", text)
        self.assertIn("frontend-design", text)
        self.assertIn("1 owning specialist", SKILL_PATH.read_text(encoding="utf-8"))

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
