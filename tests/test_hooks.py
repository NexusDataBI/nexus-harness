import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nexus_harness.hooks import completion_gate, dispatch


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


if __name__ == "__main__":
    unittest.main()
