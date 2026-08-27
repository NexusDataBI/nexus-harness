"""CLI surface for ``nexus frontend capture`` — invoke via main([...])."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from nexus_harness.__main__ import main
from nexus_harness.evidence import read_evidence
from nexus_harness.state import TaskState, load_task_state, save_task_state
from nexus_harness.visual import as_visual_evidence


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_frontend_profile(root: Path) -> Path:
    profiles = root / "profiles" / "projects"
    profiles.mkdir(parents=True)
    path = profiles / "demo.toml"
    path.write_text(
        "\n".join(
            [
                "[project]",
                'id = "demo"',
                'repository = "org/demo"',
                "",
                "[components.web]",
                'paths = ["apps/web/**"]',
                "",
                "[frontend]",
                'base_url = "http://127.0.0.1:3000"',
                'readiness_url = "http://127.0.0.1:3000"',
                'visual_paths = ["apps/web/**"]',
                "",
                "[frontend.dev_server]",
                'command = ["npm", "run", "dev"]',
                "timeout_seconds = 5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


class FrontendCaptureCliTests(unittest.TestCase):
    def test_frontend_capture_missing_route_is_usage_error(self):
        code = main(["frontend", "capture"])
        self.assertEqual(code, 2)

    def test_frontend_group_without_subcommand_is_usage_error(self):
        code = main(["frontend"])
        self.assertEqual(code, 2)

    def test_frontend_capture_runs_through_main_with_injected_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _write_frontend_profile(root)
            artifacts = root / "artifacts"
            seen: list[list[str]] = []

            def runner(argv, *, cwd=None):
                seen.append(list(argv))
                return 0, "", ""

            code = main(
                [
                    "--project-root",
                    str(root),
                    "frontend",
                    "capture",
                    "--route",
                    "/inbox",
                    "--task-id",
                    "qa-1",
                ],
                runner=runner,
                profile_path=profile,
                artifact_root=artifacts,
                probe=True,
            )
            self.assertEqual(code, 0)
            self.assertEqual(len(seen), 1)
            argv = seen[0]
            self.assertIsInstance(argv, list)
            self.assertIn("playwright", argv)
            self.assertIn("/inbox", argv)
            self.assertTrue(artifacts.is_dir())
            configs = list(artifacts.rglob("nexus.config.ts"))
            self.assertEqual(len(configs), 1)
            text = configs[0].read_text(encoding="utf-8")
            self.assertIn("http://127.0.0.1:3000", text)
            ledgers = list(artifacts.rglob("evidence.jsonl"))
            self.assertEqual(len(ledgers), 1)
            records = read_evidence(ledgers[0])
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].exit_code, 0)
            self.assertIn("playwright", records[0].command.lower())

    def test_frontend_capture_rejects_unsafe_route_without_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _write_frontend_profile(root)
            runner = Mock(side_effect=AssertionError("runner must not run"))
            code = main(
                [
                    "--project-root",
                    str(root),
                    "frontend",
                    "capture",
                    "--route",
                    "../escape",
                    "--task-id",
                    "qa-1",
                ],
                runner=runner,
                profile_path=profile,
                artifact_root=root / "artifacts",
            )
            self.assertEqual(code, 2)
            runner.assert_not_called()

    def test_frontend_capture_rejects_protocol_relative_route_without_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _write_frontend_profile(root)
            runner = Mock(side_effect=AssertionError("runner must not run"))
            code = main(
                [
                    "--project-root",
                    str(root),
                    "frontend",
                    "capture",
                    "--route",
                    "//evil.test",
                    "--task-id",
                    "qa-1",
                ],
                runner=runner,
                profile_path=profile,
                artifact_root=root / "artifacts",
            )
            self.assertEqual(code, 2)
            runner.assert_not_called()

    def test_frontend_capture_rejects_parent_task_id_without_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _write_frontend_profile(root)
            runner = Mock(side_effect=AssertionError("runner must not run"))
            code = main(
                [
                    "--project-root",
                    str(root),
                    "frontend",
                    "capture",
                    "--route",
                    "/inbox",
                    "--task-id",
                    "../evil",
                ],
                runner=runner,
                profile_path=profile,
                artifact_root=root / "artifacts",
            )
            self.assertEqual(code, 2)
            runner.assert_not_called()
            self.assertFalse((root / "evil").exists())

    def test_frontend_capture_rejects_absolute_task_id_without_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _write_frontend_profile(root)
            runner = Mock(side_effect=AssertionError("runner must not run"))
            code = main(
                [
                    "--project-root",
                    str(root),
                    "frontend",
                    "capture",
                    "--route",
                    "/inbox",
                    "--task-id",
                    "/tmp/out",
                ],
                runner=runner,
                profile_path=profile,
                artifact_root=root / "artifacts",
            )
            self.assertEqual(code, 2)
            runner.assert_not_called()

    def test_frontend_capture_refuses_when_localhost_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _write_frontend_profile(root)
            runner = Mock(side_effect=AssertionError("runner must not run"))

            class DeadProcess:
                pid = 8
                returncode = 1

                def poll(self):
                    return 1

            code = main(
                [
                    "--project-root",
                    str(root),
                    "frontend",
                    "capture",
                    "--route",
                    "/inbox",
                    "--task-id",
                    "qa-1",
                ],
                runner=runner,
                profile_path=profile,
                artifact_root=root / "artifacts",
                probe=False,
                popen=lambda *a, **k: DeadProcess(),
            )
            self.assertEqual(code, 1)
            runner.assert_not_called()

    def test_frontend_capture_passes_project_root_cwd_to_ensure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _write_frontend_profile(root)
            seen = []

            class DeadProcess:
                pid = 8
                returncode = 1

                def poll(self):
                    return 1

            def popen(argv, **kwargs):
                seen.append(dict(kwargs))
                return DeadProcess()

            runner = Mock(side_effect=AssertionError("runner must not run"))
            code = main(
                [
                    "--project-root",
                    str(root),
                    "frontend",
                    "capture",
                    "--route",
                    "/inbox",
                    "--task-id",
                    "qa-1",
                ],
                runner=runner,
                profile_path=profile,
                artifact_root=root / "artifacts",
                probe=False,
                popen=popen,
            )
            self.assertEqual(code, 1)
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0].get("cwd"), str(root.resolve()))
            runner.assert_not_called()

    def test_frontend_capture_binds_visual_paths_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = _write_frontend_profile(root)
            state_file = root / ".nexus" / "tasks" / "qa-1" / "state.json"
            state = TaskState.new("qa-1", "demo")
            state.current_diff_hash = "abc123"
            state.changed_paths = ["apps/web/page.tsx"]
            save_task_state(state, state_file)

            def runner(argv, *, cwd=None):
                return 0, "", ""

            code = main(
                [
                    "--project-root",
                    str(root),
                    "frontend",
                    "capture",
                    "--route",
                    "/inbox",
                    "--task-id",
                    "qa-1",
                ],
                runner=runner,
                profile_path=profile,
                artifact_root=root / "artifacts",
                probe=True,
            )
            self.assertEqual(code, 0)
            loaded = load_task_state(state_file)
            self.assertEqual(list(loaded.visual_paths), ["apps/web/**"])
            self.assertEqual(list(loaded.changed_paths), ["apps/web/page.tsx"])
            self.assertEqual(len(loaded.visual_evidence), 2)
            viewports = {
                as_visual_evidence(item).viewport for item in loaded.visual_evidence
            }
            self.assertEqual(viewports, {"desktop", "mobile"})

    def test_frontend_capture_discovers_single_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_frontend_profile(root)
            seen: list[list[str]] = []

            def runner(argv, *, cwd=None):
                seen.append(list(argv))
                return 0, "", ""

            code = main(
                [
                    "--project-root",
                    str(root),
                    "frontend",
                    "capture",
                    "--route",
                    "/",
                ],
                runner=runner,
                artifact_root=root / "artifacts",
                probe=True,
            )
            self.assertEqual(code, 0)
            self.assertEqual(len(seen), 1)

    def test_wrapper_still_execs_module(self):
        wrapper = REPO_ROOT / "scripts" / "nexus"
        self.assertTrue(wrapper.is_file())
        text = wrapper.read_text(encoding="utf-8")
        self.assertIn("python3 -m nexus_harness", text)


class FrontendCaptureCliJsonSmokeTests(unittest.TestCase):
    def test_help_surface_mentions_frontend_capture(self):
        parser_source = (REPO_ROOT / "src" / "nexus_harness" / "__main__.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"frontend"', parser_source)
        self.assertIn('"capture"', parser_source)
        self.assertIn("--route", parser_source)
        self.assertIn("--task-id", parser_source)
        self.assertNotIn("cypress", parser_source.lower())


if __name__ == "__main__":
    unittest.main()
