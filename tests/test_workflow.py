import tempfile
import unittest
from pathlib import Path

from nexus_harness.state import (
    AcceptanceCriterion,
    StageStatus,
    TaskState,
    load_task_state,
    save_task_state,
)
from nexus_harness.workflow import advance_stage


class WorkflowTests(unittest.TestCase):
    def test_cannot_enter_implement_without_acceptance(self):
        state = TaskState.new("task-1", "repo-1")
        state.stage = 4
        state.acceptance = []
        with self.assertRaises(ValueError):
            advance_stage(state, 5)

    def test_can_enter_implement_with_failing_acceptance(self):
        state = TaskState.new("task-1", "repo-1")
        state.stage = 4
        state.acceptance = [
            AcceptanceCriterion(id="AC-001", statement="does the thing"),
        ]

        advanced = advance_stage(state, 5)

        self.assertEqual(advanced.stage, 5)

    def test_acceptance_criterion_defaults_to_fail(self):
        criterion = AcceptanceCriterion(id="AC-001", statement="does the thing")
        self.assertEqual(criterion.status, "FAIL")

    def test_illegal_transitions_skip_ahead_and_backward(self):
        state = TaskState.new("task-1", "repo-1")
        with self.assertRaises(ValueError):
            advance_stage(state, 2)
        with self.assertRaises(ValueError):
            advance_stage(state, 9)
        state.stage = 4
        with self.assertRaises(ValueError):
            advance_stage(state, 3)

    def test_new_initializes_all_stage_status_pending(self):
        state = TaskState.new("task-1", "repo-1")
        expected = {str(stage): StageStatus.PENDING for stage in range(10)}
        self.assertEqual(state.stage_status, expected)
        self.assertEqual(set(state.stage_status), {str(stage) for stage in range(10)})

    def test_save_load_roundtrip(self):
        state = TaskState.new("task-1", "repo-1")
        state.stage = 3
        state.intent = "inspect"
        state.acceptance = [
            AcceptanceCriterion(id="AC-001", statement="does the thing"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            save_task_state(state, path)
            loaded = load_task_state(path)
        self.assertEqual(loaded.task_id, "task-1")
        self.assertEqual(loaded.repo_id, "repo-1")
        self.assertEqual(loaded.stage, 3)
        self.assertEqual(len(loaded.acceptance), 1)
        self.assertEqual(loaded.acceptance[0].id, "AC-001")
        self.assertEqual(loaded.acceptance[0].status, "FAIL")
        self.assertEqual(loaded.stage_status, state.stage_status)
        self.assertEqual(loaded.intent, "inspect")

    def test_inspect_may_enter_implement_without_acceptance(self):
        state = TaskState.new("task-1", "repo-1")
        state.stage = 4
        state.intent = "inspect"
        state.acceptance = []
        advanced = advance_stage(state, 5)
        self.assertEqual(advanced.stage, 5)

    def test_stage_8_rejects_empty_acceptance(self):
        state = TaskState.new("task-1", "repo-1")
        state.stage = 7
        state.acceptance = []
        with self.assertRaisesRegex(ValueError, "completion gate not satisfied"):
            advance_stage(state, 8)

    def test_stage_8_rejects_fail_acceptance(self):
        state = TaskState.new("task-1", "repo-1")
        state.stage = 7
        state.acceptance = [
            AcceptanceCriterion(id="AC-001", statement="does the thing"),
        ]
        with self.assertRaisesRegex(ValueError, "completion gate not satisfied"):
            advance_stage(state, 8)


if __name__ == "__main__":
    unittest.main()
