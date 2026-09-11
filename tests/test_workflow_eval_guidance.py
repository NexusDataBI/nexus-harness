import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "skills/nexus-workflow/SKILL.md"
EVAL_REF = ROOT / "skills/nexus-workflow/references/evals.md"


class WorkflowEvalGuidanceTests(unittest.TestCase):
    def test_workflow_routes_harness_behavior_changes_to_evals(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Behavioral eval gate", text)
        self.assertIn("Harness behavior", text)
        self.assertIn("references/evals.md", text)
        self.assertIn("baseline/RED", text)
        self.assertIn("deterministic regression suite", text)

    def test_eval_reference_separates_harness_from_product_tests(self):
        self.assertTrue(EVAL_REF.is_file())
        text = EVAL_REF.read_text(encoding="utf-8")
        self.assertIn("do not** need a Harness eval", text)
        self.assertIn("TDD/project tests", text)
        self.assertIn("remote mutation", text)
        self.assertIn("live/paid model", text)
        self.assertIn("permanent regression case", text)
