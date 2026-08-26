import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from nexus_harness.hooks import completion_gate, dispatch, session_start
from nexus_harness.memory.freshness import AuthorityContradiction, TruthStrength
from nexus_harness.memory.models import MemoryDraft


class HookTests(unittest.TestCase):
    @patch("nexus_harness.hooks.load_current_task")
    def test_completion_hook_blocks_failed_task(self, load_task):
        load_task.return_value = {"completion_status": "FAIL", "reasons": ["AC-1"]}
        result = completion_gate({})
        self.assertEqual(result.exit_code, 2)

    @patch("nexus_harness.hooks.load_current_task")
    @patch("nexus_harness.hooks.consolidate_memory")
    def test_failed_completion_does_not_consolidate(self, consolidate, load_task):
        load_task.return_value = {"completion_status": "FAIL", "reasons": ["AC-1"]}
        result = dispatch("TaskCompleted", {"candidates": []})
        self.assertEqual(result.exit_code, 2)
        consolidate.assert_not_called()

    @patch("nexus_harness.hooks.evaluate_completion")
    @patch("nexus_harness.hooks.collect_memory_candidates")
    @patch("nexus_harness.hooks.consolidate_memory")
    def test_ready_completion_consolidates_after_gate(
        self, consolidate, collect, evaluate
    ):
        evaluate.return_value = type(
            "Result", (), {"status": "READY_TO_SHIP", "reasons": []}
        )()
        collect.return_value = ["candidate"]
        result = dispatch(
            "TaskCompleted",
            {
                "task": {"task_id": "t", "repo_id": "r"},
                "project_root": tempfile.gettempdir(),
                "current_commit": "base",
                "signals": [],
            },
        )
        self.assertEqual(result.exit_code, 0)
        collect.assert_called_once()
        consolidate.assert_called_once()

    def test_session_start_without_memory_is_fail_soft(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = dispatch(
                "SessionStart",
                {
                    "project_root": Path(tmp),
                    "project_id": "repo",
                    "query": "task",
                },
            )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("capsule", result.output)

    @patch("nexus_harness.hooks.save_task_state")
    @patch("nexus_harness.hooks.checkpoint_memory_candidates")
    def test_precompact_checkpoints_state_and_candidates(self, checkpoint, save):
        result = dispatch(
            "PreCompact",
            {
                "task": {"task_id": "t", "repo_id": "r", "completion_status": "FAIL"},
                "state_path": "/tmp/state.json",
                "candidate_path": "/tmp/candidates.json",
                "candidates": [],
            },
        )
        self.assertEqual(result.exit_code, 0)
        save.assert_called_once()
        checkpoint.assert_called_once()

    @patch("nexus_harness.hooks.evaluate_completion")
    @patch("nexus_harness.hooks.consolidate_memory")
    def test_completion_accepts_json_signal_dicts(self, consolidate, evaluate):
        evaluate.return_value = type(
            "Result", (), {"status": "READY_TO_SHIP", "reasons": []}
        )()
        result = dispatch(
            "TaskCompleted",
            {
                "task": {"task_id": "t", "repo_id": "r"},
                "project_root": tempfile.gettempdir(),
                "base_commit": "base",
                "signals": [
                    {
                        "kind": "invariant",
                        "title": "Safe sessions",
                        "statement": "Sessions remain isolated.",
                        "sources": [{"kind": "approved_spec", "ref": "SPEC-1"}],
                    }
                ],
            },
        )
        self.assertEqual(result.exit_code, 0)
        consolidate.assert_called_once()
        self.assertIsInstance(consolidate.call_args.args[1][0], MemoryDraft)

    def test_stop_same_generation_is_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"project_root": tmp, "event_id": "same-generation"}
            with patch("nexus_harness.hooks.policy_gate") as gate:
                gate.return_value = type("Result", (), {"exit_code": 0, "output": {}})()
                first = dispatch("Stop", payload)
                second = dispatch("Stop", payload)
        self.assertEqual(first.exit_code, 0)
        self.assertTrue(second.output["loop_protected"])
        self.assertEqual(gate.call_count, 1)

    def test_compact_session_start_restores_candidates_and_invalid_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidate_path = Path(tmp) / "candidates.json"
            candidate_path.write_text("[]", encoding="utf-8")
            invalid = Path(tmp) / ".nexus" / "memory" / "invariants"
            invalid.mkdir(parents=True)
            (invalid / "bad.md").write_text("Never inject this", encoding="utf-8")
            (invalid / "bad.json").write_text("{", encoding="utf-8")
            result = session_start(
                {
                    "project_root": tmp,
                    "project_id": "repo",
                    "compact": True,
                    "candidate_path": candidate_path,
                    "query": "invalid",
                }
            )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output["candidate_count"], 0)
        self.assertNotIn("Never inject this", result.output["capsule"])
        self.assertTrue(
            result.output["warnings"] or "excluded" in result.output["capsule"]
        )

    def test_contradiction_is_forwarded_without_injecting_body(self):
        contradiction = AuthorityContradiction(
            memory_id="mem-x", authority=TruthStrength.CURRENT_REPO, pointer="src/x.py"
        )
        with patch("nexus_harness.hooks.session_recall") as recall:
            recall.return_value = type("Capsule", (), {"text": "safe capsule"})()
            result = session_start(
                {
                    "project_root": tempfile.gettempdir(),
                    "project_id": "repo",
                    "query": "x",
                    "contradictions": [contradiction],
                }
            )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(recall.call_args.kwargs["contradictions"], (contradiction,))

    def test_wrapper_output_is_json_serializable(self):
        result = dispatch("ConfigChange", {"drift": True})
        encoded = json.dumps(result.output)
        self.assertIn("drift", encoded)


if __name__ == "__main__":
    unittest.main()
