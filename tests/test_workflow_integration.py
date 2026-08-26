import tempfile
import unittest
from pathlib import Path

from nexus_harness.completion import evaluate_completion, promote_acceptance
from nexus_harness.evidence import Evidence, append_evidence, read_evidence
from nexus_harness.graph import GraphNode, TaskGraph
from nexus_harness.quality import Metric, evaluate_report
from nexus_harness.security import normalize_trivy
from nexus_harness.state import AcceptanceCriterion, TaskState


class WorkflowIntegrationTests(unittest.TestCase):
    def test_ready_to_ship_then_stale_evidence_fails(self):
        state = TaskState.new("task-1", "repo-1")
        self.assertNotEqual(state.intent, "inspect")

        state.tracking_required = True
        state.issue = 123
        state.current_diff_hash = "abc"
        state.acceptance = [
            AcceptanceCriterion(id="AC-001", statement="does the thing"),
        ]
        self.assertEqual(state.acceptance[0].status, "FAIL")

        graph = TaskGraph(
            [
                GraphNode(
                    "backend",
                    kind="implementation",
                    reads=("shared/schema.ts",),
                    writes=("apps/server/a.ts",),
                ),
                GraphNode(
                    "frontend",
                    kind="implementation",
                    reads=("shared/schema.ts",),
                    writes=("apps/web/a.ts",),
                ),
            ]
        )
        self.assertEqual(
            {node.id for node in graph.ready_nodes()}, {"backend", "frontend"}
        )
        self.assertEqual(graph.conflicts(), set())

        evidence = Evidence("ev-1", "vitest", 0, "abc", "base-1", "tests pass")
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "evidence.jsonl"
            append_evidence(ledger_path, evidence)
            ledger = read_evidence(ledger_path)
            self.assertEqual(ledger[0].id, "ev-1")
            self.assertEqual(ledger[0].exit_code, 0)
            self.assertTrue(ledger[0].is_fresh("abc"))
            state.evidence = ledger
            promote_acceptance(state, evidence)

        self.assertEqual(state.acceptance[0].status, "PASS")
        self.assertEqual(state.acceptance[0].evidence, "ev-1")

        quality = evaluate_report(
            [
                Metric(
                    "coverage",
                    current=81.0,
                    baseline=80.0,
                    mode="ratchet",
                    direction="higher",
                ),
                Metric(
                    "failing_tests",
                    current=0,
                    threshold=0,
                    mode="absolute",
                    direction="lower",
                ),
            ],
            diff_hash="abc",
        )
        security = normalize_trivy({"Results": []}, diff_hash="abc")
        self.assertEqual(quality.gate, "PASS")
        self.assertEqual(security.gate, "PASS")

        state.quality_gate = quality
        state.security_gate = security
        state.review_gate = "PASS"
        state.verified_diff_hash = "abc"
        state.reviewed_diff_hash = "abc"
        state.findings = []

        ready = evaluate_completion(state)
        self.assertEqual(ready.status, "READY_TO_SHIP")
        self.assertEqual(ready.reasons, [])

        state.current_diff_hash = "def"
        stale = evaluate_completion(state)
        self.assertEqual(stale.status, "FAIL")
        self.assertTrue(any("evidence" in reason for reason in stale.reasons))


if __name__ == "__main__":
    unittest.main()
