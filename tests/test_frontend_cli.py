"""CLI surface for ``nexus frontend capture`` — invoke via main([...])."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from nexus_harness.__main__ import main
from nexus_harness.evidence import read_evidence


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
