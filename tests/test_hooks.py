from dataclasses import replace
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nexus_harness.hooks import _root, completion_gate, dispatch, session_start
import nexus_harness.hooks as hooks_mod
import nexus_harness.memory as memory_mod
from nexus_harness.memory.freshness import AuthorityContradiction, TruthStrength
from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.store import init_project_memory, write_memory
from nexus_harness.state import TaskState


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

    @patch("nexus_harness.hooks.verify_git_oid", return_value="abc")
    @patch("nexus_harness.hooks.evaluate_completion")
    @patch("nexus_harness.hooks.collect_memory_candidates")
    @patch("nexus_harness.hooks.consolidate_memory")
    def test_ready_completion_consolidates_after_gate(
        self, consolidate, collect, evaluate, _oid
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
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.dict(os.environ, {"NEXUS_RUNTIME_HOME": tmp}):
                result = dispatch(
                    "PreCompact",
                    {
                        "task": {
                            "task_id": "t",
                            "repo_id": "r",
                            "completion_status": "FAIL",
                        },
                        "state_path": str(home / "task-state.json"),
                        "candidate_path": str(home / "memory-candidates.json"),
                        "candidates": [],
                    },
                )
        self.assertEqual(result.exit_code, 0)
        save.assert_called_once()
        checkpoint.assert_called_once()

    @patch("nexus_harness.hooks.verify_git_oid", return_value="abc")
    @patch("nexus_harness.hooks.evaluate_completion")
    @patch("nexus_harness.hooks.collect_memory_candidates")
    @patch("nexus_harness.hooks.consolidate_memory")
    def test_completion_ignores_payload_signals_and_candidates(
        self, consolidate, collect, evaluate, _oid
    ):
        evaluate.return_value = type(
            "Result", (), {"status": "READY_TO_SHIP", "reasons": []}
        )()
        collect.return_value = []
        result = dispatch(
            "TaskCompleted",
            {
                "task": {"task_id": "t", "repo_id": "r"},
                "project_root": tempfile.gettempdir(),
                "base_commit": "forged",
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
        collect.assert_called_once()
        self.assertEqual(collect.call_args.kwargs["signals"], ())
        consolidate.assert_called_once()

    def test_pretooluse_requires_tool_name_and_allows_failed_task(self):
        missing = dispatch("PreToolUse", {})
        failed = dispatch(
            "PreToolUse",
            {
                "tool_name": "Read",
                "tool_input": {"path": "README.md"},
                "task": {"completion_status": "FAIL", "reasons": ["AC-1"]},
            },
        )
        self.assertEqual(missing.exit_code, 2)
        self.assertEqual(failed.exit_code, 0)

    def test_pretooluse_denies_only_when_payload_sets_deny(self):
        allowed = dispatch(
            "PreToolUse",
            {"deny": False, "tool_name": "Read", "tool_input": {}},
        )
        denied = dispatch("PreToolUse", {"deny": True})
        self.assertEqual(allowed.exit_code, 0)
        self.assertEqual(denied.exit_code, 2)

    def test_stop_same_generation_repeats_blocking_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "project_root": tmp,
                "event_id": "same-generation",
                "repo_id": "repo",
                "task_id": "task",
                "task": {"completion_status": "FAIL", "reasons": ["AC-1"]},
            }
            with patch.dict(os.environ, {"NEXUS_RUNTIME_HOME": tmp}):
                first = dispatch("Stop", payload)
                second = dispatch("Stop", payload)
        self.assertEqual(first.exit_code, 2)
        self.assertEqual(second.exit_code, 2)
        self.assertTrue(second.output["loop_protected"])
        self.assertEqual(second.output["reasons"], ["AC-1"])

    def test_stop_without_identity_is_never_globally_debounced(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("nexus_harness.hooks.completion_gate") as gate:
                gate.return_value = type("Result", (), {"exit_code": 0, "output": {}})()
                first = dispatch("Stop", {"project_root": tmp})
                second = dispatch("Stop", {"project_root": tmp})
        self.assertFalse(first.output.get("loop_protected", False))
        self.assertFalse(second.output.get("loop_protected", False))
        self.assertEqual(gate.call_count, 2)

    def test_stop_without_identity_runs_fail_closed_completion_gate(self):
        result = dispatch(
            "Stop",
            {"task": {"completion_status": "FAIL", "reasons": ["AC-1"]}},
        )
        self.assertEqual(result.exit_code, 2)
        self.assertFalse(result.output.get("loop_protected", False))

    def test_stop_io_and_corrupt_marker_still_run_completion_gate(self):
        failing_task = {"completion_status": "FAIL", "reasons": ["AC-1"]}
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "runtime"
            with patch.dict(os.environ, {"NEXUS_RUNTIME_HOME": str(home)}):
                io_dir = home / "stop"
                io_dir.mkdir(parents=True)
                (io_dir / "unscoped.json").mkdir()
                io_result = dispatch(
                    "Stop",
                    {
                        "project_root": tmp,
                        "session_id": "session-io",
                        "task": failing_task,
                    },
                )
                corrupt_home = Path(tmp) / "corrupt"
                marker = corrupt_home / "stop" / "unscoped.json"
                marker.parent.mkdir(parents=True)
                marker.write_text("{", encoding="utf-8")
                with patch.dict(os.environ, {"NEXUS_RUNTIME_HOME": str(corrupt_home)}):
                    corrupt_result = dispatch(
                        "Stop",
                        {
                            "project_root": tmp,
                            "session_id": "session-corrupt",
                            "task": failing_task,
                        },
                    )
        self.assertEqual(io_result.exit_code, 2)
        self.assertFalse(io_result.output.get("loop_protected", False))
        self.assertEqual(corrupt_result.exit_code, 2)
        self.assertFalse(corrupt_result.output.get("loop_protected", False))

    def test_session_start_excludes_candidate_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            draft = MemoryDraft(
                type=MemoryType.INVARIANT,
                scope=MemoryScope.PROJECT,
                project_id="repo",
                title="Candidate only",
                body="Do not inject this candidate.",
                sources=(MemorySource("approved_spec", "SPEC-1"),),
            )
            write_memory(root, draft.to_record())
            result = session_start(
                {"project_root": root, "project_id": "repo", "query": "candidate"}
            )
        self.assertNotIn("Do not inject this candidate.", result.output["capsule"])

    def test_compact_session_start_restores_candidates_and_invalid_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "runtime"
            home.mkdir()
            candidate_path = home / "candidates.json"
            candidate_path.write_text("[]", encoding="utf-8")
            invalid = Path(tmp) / ".nexus" / "memory" / "invariants"
            invalid.mkdir(parents=True)
            (invalid / "bad.md").write_text("Never inject this", encoding="utf-8")
            (invalid / "bad.json").write_text("{", encoding="utf-8")
            with patch.dict(os.environ, {"NEXUS_RUNTIME_HOME": str(home)}):
                result = session_start(
                    {
                        "project_root": tmp,
                        "project_id": "repo",
                        "compact": True,
                        "task": {"task_id": "t", "repo_id": "repo"},
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

    def test_precompact_then_compact_session_start_restores_state_and_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            home = Path(tmp) / "runtime"
            home.mkdir()
            state_path = home / "state.json"
            candidate_path = home / "candidates.json"
            state = TaskState.new("task", "repo")
            state.completion_status = "FAIL"
            state.completion_reasons = ["AC-1"]
            draft = MemoryDraft(
                type=MemoryType.INVARIANT,
                scope=MemoryScope.PROJECT,
                project_id="repo",
                title="Invariant",
                body="Keep state structured.",
                sources=(MemorySource("approved_spec", "SPEC-1"),),
            )
            with patch.dict(os.environ, {"NEXUS_RUNTIME_HOME": str(home)}):
                self.assertEqual(
                    dispatch(
                        "PreCompact",
                        {
                            "project_root": root,
                            "state_path": state_path,
                            "candidate_path": candidate_path,
                            "task": state.to_dict(),
                            "candidates": [draft],
                        },
                    ).exit_code,
                    0,
                )
                restored = dispatch(
                    "SessionStart",
                    {
                        "project_root": root,
                        "state_path": state_path,
                        "candidate_path": candidate_path,
                        "compact": True,
                        "project_id": "repo",
                    },
                )
        self.assertEqual(restored.output["task"]["completion_status"], "FAIL")
        self.assertEqual(restored.output["task"]["completion_reasons"], ["AC-1"])
        self.assertEqual(restored.output["candidate_count"], 1)

    def test_postcompact_is_observer_only(self):
        with patch("nexus_harness.hooks.restore_memory_candidates") as restore:
            result = dispatch("PostCompact", {"compact": True})
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.output["restored"])
        restore.assert_not_called()

    def test_claude_source_compact_restores_candidates_without_compact_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "runtime"
            home.mkdir()
            candidate_path = home / "candidates.json"
            candidate_path.write_text("[]", encoding="utf-8")
            with patch.dict(os.environ, {"NEXUS_RUNTIME_HOME": str(home)}):
                result = session_start(
                    {
                        "project_root": tmp,
                        "project_id": "repo",
                        "source": "compact",
                        "task": {"task_id": "t", "repo_id": "repo"},
                        "candidate_path": candidate_path,
                        "query": "compact",
                        "cache_home": Path(tmp) / "cache",
                    }
                )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output["candidate_count"], 0)

    def test_user_prompt_submit_uses_claude_prompt_as_query(self):
        with patch("nexus_harness.hooks.session_recall") as recall:
            recall.return_value = type("Capsule", (), {"text": "warm capsule"})()
            result = dispatch(
                "UserPromptSubmit",
                {
                    "project_root": tempfile.gettempdir(),
                    "project_id": "repo",
                    "prompt": "warm query from claude",
                },
            )
        self.assertTrue(result.output["refreshed"])
        self.assertEqual(recall.call_args.kwargs["query"], "warm query from claude")

    def test_user_prompt_submit_classification_sees_prompt(self):
        prompt = "warm query from claude"
        result = dispatch(
            "UserPromptSubmit",
            {
                "prompt": prompt,
                "previous_classification": {
                    "query": prompt,
                    "affected_paths": [],
                    "domain": None,
                },
            },
        )
        self.assertEqual(result.output, {"refreshed": False})

    def test_session_start_excludes_current_repo_contradiction_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "isolated-home"
            cache = root / "cache"
            home.mkdir()
            init_project_memory(root)
            record = write_memory(
                root,
                replace(
                    MemoryDraft(
                        type=MemoryType.INVARIANT,
                        scope=MemoryScope.PROJECT,
                        project_id="repo",
                        title="Auth isolation",
                        body="CONTRADICTED-BODY-MUST-NOT-APPEAR",
                        sources=(MemorySource("approved_spec", "SPEC-1"),),
                    ).to_record(),
                    status=MemoryStatus.VERIFIED,
                    confidence=MemoryConfidence.HIGH,
                    verified_at="2026-08-25T00:00:00Z",
                ),
            )
            contradiction = AuthorityContradiction(
                memory_id=record.id,
                authority=TruthStrength.CURRENT_REPO,
                pointer="src/auth/session.py",
            )
            with patch.dict(os.environ, {"HOME": str(home)}):
                result = session_start(
                    {
                        "project_root": root,
                        "project_id": "repo",
                        "query": "auth isolation",
                        "cache_home": cache,
                        "contradictions": [contradiction],
                    }
                )
            self.assertFalse((home / ".nexus-harness").exists())
        self.assertEqual(result.exit_code, 0)
        capsule = result.output["capsule"]
        self.assertNotIn("CONTRADICTED-BODY-MUST-NOT-APPEAR", capsule)
        self.assertIn("src/auth/session.py", capsule)
        self.assertIn(record.id, capsule)

    def test_hooks_import_public_memory_api_only(self):
        source = inspect.getsource(hooks_mod)
        self.assertNotIn("nexus_harness.memory.lifecycle", source)
        self.assertNotIn("nexus_harness.memory.models", source)
        self.assertIn("CandidateSignal", memory_mod.__all__)
        self.assertTrue(hasattr(memory_mod, "CandidateSignal"))

    def test_root_reads_cwd_after_project_and_repo_roots(self):
        self.assertEqual(
            _root({"cwd": "/tmp/from-cwd"}), Path("/tmp/from-cwd").resolve()
        )
        self.assertEqual(
            _root({"repo_root": "/tmp/repo", "cwd": "/tmp/from-cwd"}),
            Path("/tmp/repo").resolve(),
        )
        self.assertEqual(
            _root(
                {
                    "project_root": "/tmp/project",
                    "repo_root": "/tmp/repo",
                    "cwd": "/tmp/from-cwd",
                }
            ),
            Path("/tmp/project").resolve(),
        )

    def test_precompact_without_task_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = dispatch("PreCompact", {"project_root": tmp})
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.output["checkpointed"], False)

    def test_task_id_mismatch_blocks_task_completed(self):
        result = dispatch(
            "TaskCompleted",
            {
                "task_id": "other",
                "task": {"task_id": "t", "repo_id": "r", "completion_status": "FAIL"},
            },
        )
        self.assertEqual(result.exit_code, 2)
        self.assertIn("mismatch", result.output["reasons"][0])

    def test_task_state_schema_includes_completion_fields(self):
        schema = json.loads(
            Path("core/workflow/task-state.schema.json").read_text(encoding="utf-8")
        )
        self.assertIn("completion_status", schema["properties"])
        self.assertIn("completion_reasons", schema["properties"])

    def test_wrapper_output_is_json_serializable(self):
        result = dispatch("ConfigChange", {"drift": True})
        encoded = json.dumps(result.output)
        self.assertIn("drift", encoded)


if __name__ == "__main__":
    unittest.main()
