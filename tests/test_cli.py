"""CLI entrypoint tests — python3 -m nexus_harness (no real docker/git required)."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock

from nexus_harness.__main__ import main
from nexus_harness.state import TaskState, save_task_state

REPO_ROOT = Path(__file__).resolve().parents[1]
SDR_PROFILE = REPO_ROOT / "profiles" / "projects" / "sdr-platform.toml"

CORE_COMMANDS = (
    "validate",
    "build",
    "install",
    "doctor",
    "workflow",
    "quality",
    "project",
    "frontend",
    "incidents",
    "evals",
)


def _run_main(argv, **kwargs):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv, **kwargs)
    return code, stdout.getvalue(), stderr.getvalue()


class CliAffectedTests(unittest.TestCase):
    def test_ci_affected_writes_plan_with_fake_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out = tmp_path / "affected.json"

            def fake_git(base: str, head: str, cwd: Path) -> tuple[str, ...]:
                self.assertEqual(base, "aaa")
                self.assertEqual(head, "bbb")
                return ("apps/web/src/app.tsx",)

            code = main(
                [
                    "--project-root",
                    str(REPO_ROOT),
                    "ci",
                    "affected",
                    "--base",
                    "aaa",
                    "--head",
                    "bbb",
                    "--output",
                    str(out),
                ],
                git_diff=fake_git,
                profile_path=SDR_PROFILE,
            )
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("web", payload["components"])
            self.assertIn("web", payload["images"])
            self.assertNotIn("server", payload["images"])


class CliQualityTests(unittest.TestCase):
    def test_quality_run_empty_affected_is_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan_path = tmp_path / "affected.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "components": [],
                        "checks": [],
                        "images": [],
                        "unmatched": [],
                    }
                ),
                encoding="utf-8",
            )

            def boom(*a, **k):
                raise AssertionError("runner must not run for empty affected")

            code = main(
                [
                    "--project-root",
                    str(tmp_path),
                    "quality",
                    "run",
                    "--profile",
                    "standard",
                    "--from-affected",
                    str(plan_path),
                ],
                runner=boom,
            )
            self.assertEqual(code, 0)


class CliImagesTests(unittest.TestCase):
    def test_images_build_dry_run_uses_profile_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan_path = tmp_path / "affected.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "components": ["web"],
                        "checks": [],
                        "images": ["web"],
                        "unmatched": [],
                    }
                ),
                encoding="utf-8",
            )
            code = main(
                [
                    "--project-root",
                    str(REPO_ROOT),
                    "images",
                    "build",
                    "--from-affected",
                    str(plan_path),
                    "--dry-run",
                ],
                profile_path=SDR_PROFILE,
            )
            self.assertEqual(code, 0)


class ScriptsNexusWrapperTests(unittest.TestCase):
    def test_wrapper_execs_module(self):
        wrapper = REPO_ROOT / "scripts" / "nexus"
        self.assertTrue(wrapper.is_file())
        text = wrapper.read_text(encoding="utf-8")
        self.assertIn("python3 -m nexus_harness", text)
        self.assertIn("PYTHONPATH", text)
        self.assertIn("python3 -m nexus_harness.cli", text)


class CliHelpTests(unittest.TestCase):
    def test_help_lists_core_commands(self):
        result = subprocess.run(
            ["bash", str(REPO_ROOT / "scripts" / "nexus"), "--help"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in CORE_COMMANDS:
            self.assertIn(name, result.stdout)


class CliEvalsTests(unittest.TestCase):
    def test_evals_run_exits_zero_on_pass(self):
        code, stdout, stderr = _run_main(
            ["--project-root", str(REPO_ROOT), "evals", "run"]
        )
        self.assertEqual(code, 0, stderr + stdout)
        self.assertRegex(stdout + stderr, r"\bPASS\b")
        self.assertRegex(stdout + stderr, r"model-quality")
        self.assertRegex(stdout + stderr, r"\bSKIP\b")


class CliValidateJsonTests(unittest.TestCase):
    def test_validate_json_writes_report_on_stdout_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = _run_main(
                ["--json", "--project-root", tmp, "validate"]
            )
        self.assertNotEqual(code, 0)
        payload = json.loads(stdout)
        self.assertIn("errors", payload)
        self.assertTrue(payload["errors"])
        self.assertFalse(payload["ok"])
        self.assertEqual(stderr.strip(), "")
        self.assertNotIn("phx_", stdout)
        self.assertNotIn("ghp_", stdout)
        self.assertNotIn("github_pat_", stdout)


class CliWorkflowTests(unittest.TestCase):
    def test_workflow_advance_writes_next_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            save_task_state(TaskState.new("task-1", "repo-1"), path)
            code, stdout, stderr = _run_main(
                [
                    "--json",
                    "workflow",
                    "advance",
                    "--state",
                    str(path),
                    "--to",
                    "1",
                ]
            )
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["stage"], 1)
            self.assertEqual(payload["task_id"], "task-1")
            self.assertEqual(stderr.strip(), "")


class CliProjectTests(unittest.TestCase):
    def test_project_show_by_id_json(self):
        code, stdout, stderr = _run_main(
            [
                "--json",
                "--project-root",
                str(REPO_ROOT),
                "project",
                "show",
                "--id",
                "sdr-platform",
            ]
        )
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["id"], "sdr-platform")
        self.assertEqual(payload["repository"], "Rubens-Marques/SDR-Plataform")
        self.assertNotIn("token", json.dumps(payload).casefold())
        self.assertEqual(stderr.strip(), "")


class CliIncidentsTests(unittest.TestCase):
    def test_incidents_render_is_local_and_does_not_mutate(self):
        github = Mock()
        problem = {
            "project": "sdr-platform",
            "environment": "production",
            "error_type": "TypeError",
            "stack_location": "src/leads.ts:fetchLead",
            "route": "/api/leads",
            "occurrences": 4,
            "affected_users": 3,
            "token": "ghp_should_never_appear",
            "personal_api_key": "phx_should_never_appear",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "problem.json"
            path.write_text(json.dumps(problem), encoding="utf-8")
            code, stdout, stderr = _run_main(
                ["--json", "incidents", "render", "--input", str(path)],
                github=github,
            )
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertFalse(payload["mutated"])
        body = payload["request_body"]
        self.assertIn("TypeError", body)
        self.assertNotIn("ghp_should_never_appear", stdout)
        self.assertNotIn("phx_should_never_appear", stdout)
        github.create_issue.assert_not_called()
        github.edit_issue.assert_not_called()
        github.api.assert_not_called()
        self.assertEqual(stderr.strip(), "")

    def test_incidents_classify_stays_policy_local(self):
        github = Mock()
        problem = {
            "project": "sdr-platform",
            "environment": "production",
            "error_type": "TypeError",
            "stack_location": "src/leads.ts:fetchLead",
            "occurrences": 1,
            "affected_users": 0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "problem.json"
            path.write_text(json.dumps(problem), encoding="utf-8")
            code, stdout, stderr = _run_main(
                ["--json", "incidents", "classify", "--input", str(path)],
                github=github,
            )
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["action"], "IGNORE")
        github.create_issue.assert_not_called()
        github.edit_issue.assert_not_called()


class CliInstallTests(unittest.TestCase):
    def test_install_copies_source_to_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "dist"
            target = root / "installed"
            source.mkdir()
            (source / "generated.txt").write_text("ok", encoding="utf-8")
            code, stdout, stderr = _run_main(
                ["--json", "install", str(source), str(target)]
            )
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(
                (target / "generated.txt").read_text(encoding="utf-8"), "ok"
            )
            self.assertIn("backup", payload)
            self.assertEqual(stderr.strip(), "")


class CliBuildAdaptersTests(unittest.TestCase):
    def test_build_adapters_compiles_project_root_not_adapters_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "core" / "constitution.md").write_text(
                "NEXUS WORKFLOW IS MANDATORY.\n", encoding="utf-8"
            )
            (root / "adapters").mkdir()
            (root / "adapters" / "trap.txt").write_text("not-a-compile-root")
            code, stdout, stderr = _run_main(
                ["--json", "--project-root", str(root), "build", "adapters"]
            )
            self.assertEqual(code, 0, stderr + stdout)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertGreater(payload["generated"], 0)
            self.assertTrue((root / "dist" / "claude" / "CLAUDE.md").is_file())
            self.assertFalse((root / "adapters" / "dist").exists())


if __name__ == "__main__":
    unittest.main()
