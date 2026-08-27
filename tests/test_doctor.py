"""Doctor diagnostics — network-free, no live GitHub/PostHog/VPS/SSH."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from nexus_harness.compile import compile_harness
from nexus_harness.doctor import (
    DoctorCheck,
    format_doctor_report,
    run_doctor,
    summarize,
)
from nexus_harness.serialize import dumps_report

CANONICAL_SKILLS = (
    "accessibility",
    "nexus-frontend",
    "nexus-handoff",
    "nexus-quality",
    "nexus-ship",
    "nexus-verify",
    "nexus-workflow",
)

REQUIRED_CHECK_NAMES = (
    "python",
    "git",
    "gh",
    "canonical-core",
    "generated-drift",
    "claude",
    "cursor",
    "codex",
    "task-state",
    "memory",
    "project-registry",
    "quality-tooling",
    "frontend-tooling",
    "trivy",
    "ci-profile",
    "github",
    "posthog",
    "release",
)

SECRET = "phx_doctor_must_never_print_this"
GITHUB_TOKEN = "ghp_doctor_must_never_print_this"


def _minimal_root(root: Path) -> Path:
    (root / "core" / "policies").mkdir(parents=True)
    (root / "core" / "memory").mkdir(parents=True)
    (root / "core" / "observability").mkdir(parents=True)
    (root / "core" / "constitution.md").write_text(
        "NEXUS WORKFLOW IS MANDATORY.\n",
        encoding="utf-8",
    )
    (root / "core" / "policies" / "production.toml").write_text(
        "[deploy]\nrequires_explicit_gate = true\n",
        encoding="utf-8",
    )
    (root / "core" / "memory" / "retrieval-policy.toml").write_text(
        "schema_version = 1\n"
        "[capsule]\n"
        "hot_max_chars = 100\n"
        "warm_max_chars = 100\n"
        "max_items = 4\n"
        "max_item_chars = 80\n",
        encoding="utf-8",
    )
    (root / "core" / "observability" / "posthog.toml").write_text(
        'enabled = false\nproject_id = ""\nhost = ""\nregion = ""\n',
        encoding="utf-8",
    )
    (root / "profiles").mkdir()
    (root / "profiles" / "default.toml").write_text(
        '[profile]\nname = "default"\n',
        encoding="utf-8",
    )
    (root / "profiles" / "projects").mkdir()
    (root / "profiles" / "projects" / "web.toml").write_text(
        "[project]\n"
        'id = "web"\n'
        'repository = "acme/web"\n'
        "[components.app]\n"
        'paths = ["apps/web/**"]\n'
        'checks = ["biome", "vitest", "playwright", "trivy"]\n',
        encoding="utf-8",
    )
    for name in CANONICAL_SKILLS:
        skill = root / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    example = root / "upstream" / "example"
    example.mkdir(parents=True)
    (example / "SKILL.md").write_text("upstream\n", encoding="utf-8")
    vendor = {
        "schema_version": 1,
        "sources": [
            {
                "id": "example",
                "kind": "export",
                "revision_kind": "content_sha256",
                "revision": "a" * 64,
                "canonical_path": "upstream/example",
            }
        ],
    }
    (root / "upstream" / "vendor-lock.json").write_text(
        json.dumps(vendor, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "projects.toml").write_text(
        "[projects.web]\n"
        'name = "Web"\n'
        'repository = "acme/web"\n'
        'client = "acme"\n'
        'status = "active"\n',
        encoding="utf-8",
    )
    (root / "dist").mkdir()
    (root / "dist" / ".gitkeep").write_bytes(b"")
    compile_harness(root)
    return root


def _which_git_only(name: str) -> str | None:
    if name == "git":
        return "/usr/bin/git"
    return None


def _run(root: Path, **kwargs):
    kwargs.setdefault("which", _which_git_only)
    kwargs.setdefault("python_version", (3, 11))
    kwargs.setdefault("environ", {})
    kwargs.setdefault("runtime_home", root / "runtime-home")
    (root / "runtime-home").mkdir(parents=True, exist_ok=True)
    return run_doctor(root, **kwargs)


def _by_name(report):
    return {check.name: check for check in report.checks}


class DoctorSummarizeTests(unittest.TestCase):
    def test_required_failure_makes_doctor_fail(self):
        result = summarize(
            [
                DoctorCheck("python", "PASS", required=True),
                DoctorCheck("generated-drift", "FAIL", required=True),
            ]
        )
        self.assertEqual(result.gate, "FAIL")

    def test_activation_required_does_not_fail_local_or_release(self):
        checks = [
            DoctorCheck("python", "PASS", required=True),
            DoctorCheck("posthog", "ACTIVATION_REQUIRED", required=True),
            DoctorCheck("github", "ACTIVATION_REQUIRED", required=True),
            DoctorCheck("ci-profile", "ACTIVATION_REQUIRED", required=True),
        ]
        for profile in ("local", "release"):
            result = summarize(checks, profile=profile)
            self.assertNotEqual(result.gate, "FAIL", profile)
            self.assertEqual(result.gate, "PASS", profile)

    def test_optional_skip_does_not_fail(self):
        result = summarize(
            [
                DoctorCheck("python", "PASS", required=True),
                DoctorCheck("playwright", "SKIP", required=False),
            ]
        )
        self.assertEqual(result.gate, "PASS")

    def test_required_warn_is_warn_not_fail(self):
        result = summarize(
            [
                DoctorCheck("python", "PASS", required=True),
                DoctorCheck("disk", "WARN", required=True),
            ]
        )
        self.assertEqual(result.gate, "WARN")


class DoctorRunTests(unittest.TestCase):
    def test_local_fixture_covers_required_checks_without_false_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            report = _run(root, profile="local")
            names = _by_name(report)
            for name in REQUIRED_CHECK_NAMES:
                self.assertIn(name, names, name)
            self.assertNotEqual(report.gate, "FAIL")
            self.assertEqual(names["python"].status, "PASS")
            self.assertEqual(names["git"].status, "PASS")
            self.assertEqual(names["canonical-core"].status, "PASS")
            self.assertEqual(names["generated-drift"].status, "PASS")
            self.assertEqual(names["project-registry"].status, "PASS")
            self.assertEqual(names["quality-tooling"].status, "SKIP")
            self.assertEqual(names["frontend-tooling"].status, "SKIP")
            self.assertEqual(names["trivy"].status, "SKIP")
            self.assertEqual(names["posthog"].status, "SKIP")
            self.assertEqual(names["github"].status, "ACTIVATION_REQUIRED")
            self.assertEqual(names["gh"].status, "ACTIVATION_REQUIRED")
            self.assertEqual(names["release"].status, "ACTIVATION_REQUIRED")

    def test_local_missing_dist_adapters_warn_release_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            for path in (root / "dist").rglob("*"):
                if path.is_file() and path.name != ".gitkeep":
                    path.unlink()
            local = _run(root, profile="local")
            self.assertEqual(_by_name(local)["claude"].status, "WARN")
            self.assertEqual(_by_name(local)["cursor"].status, "WARN")
            self.assertEqual(_by_name(local)["codex"].status, "WARN")
            self.assertNotEqual(local.gate, "FAIL")
            self.assertIn("scripts/nexus build", _by_name(local)["claude"].repair)
            release = _run(root, profile="release")
            self.assertEqual(_by_name(release)["claude"].status, "FAIL")
            self.assertEqual(release.gate, "FAIL")

    def test_python_below_floor_fails_with_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            report = _run(root, python_version=(3, 10))
            check = _by_name(report)["python"]
            self.assertEqual(check.status, "FAIL")
            self.assertEqual(report.gate, "FAIL")
            text = format_doctor_report(report)
            self.assertIn("3.11", text)
            self.assertTrue(check.repair)
            self.assertNotIn("configuration invalid", text)

    def test_generated_drift_fails_with_compile_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            target = root / "dist" / "claude" / "CLAUDE.md"
            target.write_text(target.read_text(encoding="utf-8") + "drift\n")
            report = _run(root, profile="release")
            check = _by_name(report)["generated-drift"]
            self.assertEqual(check.status, "FAIL")
            self.assertEqual(report.gate, "FAIL")
            self.assertIn("nexus", check.repair)
            self.assertTrue(
                "build" in check.repair or "compile" in check.repair,
                check.repair,
            )

    def test_missing_git_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            report = _run(root, which=lambda name: None)
            self.assertEqual(_by_name(report)["git"].status, "FAIL")
            self.assertEqual(report.gate, "FAIL")

    def test_posthog_disabled_is_not_fail_and_json_has_no_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            environ = {"POSTHOG_PERSONAL_API_KEY": SECRET}
            local = _run(root, profile="local", environ=environ)
            release = _run(root, profile="release", environ=environ)
            self.assertEqual(_by_name(local)["posthog"].status, "SKIP")
            self.assertEqual(_by_name(release)["posthog"].status, "ACTIVATION_REQUIRED")
            self.assertNotEqual(local.gate, "FAIL")
            self.assertNotEqual(release.gate, "FAIL")
            blob = dumps_report(release.to_dict())
            self.assertNotIn(SECRET, blob)
            self.assertNotIn("phx_", blob)
            self.assertNotIn(GITHUB_TOKEN, blob)
            text = format_doctor_report(release)
            self.assertNotIn(SECRET, text)
            self.assertIn("posthog.toml", text)
            self.assertIn("POSTHOG_PERSONAL_API_KEY", text)

    def test_github_live_ids_absent_are_activation_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            report = _run(root, profile="release", github_project_ids={})
            check = _by_name(report)["github"]
            self.assertEqual(check.status, "ACTIVATION_REQUIRED")
            self.assertNotEqual(report.gate, "FAIL")
            self.assertIn("project", check.repair.casefold())
            self.assertTrue(check.message)
            self.assertNotIn("configuration invalid", check.message)

    def test_ci_host_missing_runner_is_activation_required_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            report = _run(
                root,
                profile="ci-host",
                ci_facts={
                    "disk_percent": 40,
                    "memory_percent": 40,
                    "runner": False,
                    "docker": True,
                    "cache_writable": True,
                },
            )
            check = _by_name(report)["ci-profile"]
            self.assertEqual(check.status, "ACTIVATION_REQUIRED")
            self.assertNotEqual(report.gate, "FAIL")
            self.assertIn("runner", check.message.casefold())

    def test_ci_host_without_facts_is_activation_required_and_never_sshes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))

            def boom(*args, **kwargs):
                raise AssertionError(f"doctor must not spawn processes: {args!r}")

            with (
                patch("subprocess.run", side_effect=boom),
                patch("subprocess.Popen", side_effect=boom),
            ):
                report = _run(root, profile="ci-host", ci_facts=None)
            check = _by_name(report)["ci-profile"]
            self.assertEqual(check.status, "ACTIVATION_REQUIRED")
            self.assertNotEqual(report.gate, "FAIL")
            text = format_doctor_report(report)
            self.assertNotRegex(text, r"(?i)ssh://|ssh\s+\S+@")
            self.assertIn("ci-host", text.casefold())

    def test_ci_host_fixture_disk_fail_still_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            report = _run(
                root,
                profile="ci-host",
                ci_facts={"disk_percent": 96, "runner": True, "docker": True},
            )
            self.assertEqual(_by_name(report)["ci-profile"].status, "FAIL")
            self.assertEqual(report.gate, "FAIL")

    def test_quality_tools_fail_only_when_selected_project_requires_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            skipped = _run(root, profile="local", tools={})
            names = _by_name(skipped)
            self.assertEqual(names["quality-tooling"].status, "SKIP")
            self.assertEqual(names["frontend-tooling"].status, "SKIP")
            self.assertEqual(names["trivy"].status, "SKIP")

            missing = _run(
                root,
                profile="release",
                selected_project="web",
                tools={
                    "biome": False,
                    "vitest": False,
                    "playwright": False,
                    "trivy": False,
                },
            )
            required = _by_name(missing)
            self.assertEqual(required["quality-tooling"].status, "FAIL")
            self.assertEqual(required["frontend-tooling"].status, "FAIL")
            self.assertEqual(required["trivy"].status, "FAIL")
            self.assertEqual(missing.gate, "FAIL")
            self.assertIn("biome", required["quality-tooling"].repair.casefold())
            self.assertIn("playwright", required["frontend-tooling"].repair.casefold())
            self.assertIn("trivy", required["trivy"].repair.casefold())

            present = _run(
                root,
                profile="release",
                selected_project="web",
                tools={
                    "biome": True,
                    "vitest": True,
                    "playwright": True,
                    "trivy": True,
                },
            )
            ok = _by_name(present)
            self.assertEqual(ok["quality-tooling"].status, "PASS")
            self.assertEqual(ok["frontend-tooling"].status, "PASS")
            self.assertEqual(ok["trivy"].status, "PASS")

    def test_unwritable_task_state_fails_with_path_and_chmod(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            runtime = (root / "runtime-home").resolve()
            runtime.mkdir(parents=True, exist_ok=True)
            real_access = os.access

            def access(path, mode, *args, **kwargs):
                target = Path(path).resolve()
                if target == runtime and mode == os.W_OK:
                    return False
                return real_access(path, mode, *args, **kwargs)

            with patch("nexus_harness.doctor.os.access", side_effect=access):
                report = _run(root, runtime_home=runtime)
            check = _by_name(report)["task-state"]
            self.assertEqual(check.status, "FAIL")
            combined = check.message + check.repair
            self.assertIn(str(runtime), combined)
            self.assertIn("chmod", check.repair)
            self.assertIn("NEXUS_RUNTIME_HOME", check.repair)

    def test_failure_output_is_actionable_not_generic(self):
        result = summarize(
            [
                DoctorCheck(
                    "generated-drift",
                    "FAIL",
                    required=True,
                    message="generated hash drift vs harness.lock",
                    repair="scripts/nexus build",
                )
            ]
        )
        text = format_doctor_report(result)
        self.assertIn("generated-drift", text)
        self.assertIn("FAIL", text)
        self.assertIn("scripts/nexus build", text)
        self.assertIn("why", text.casefold())
        self.assertNotIn("configuration invalid", text)

    def test_invalid_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            with self.assertRaises(ValueError):
                _run(root, profile="staging")


class DoctorCliTests(unittest.TestCase):
    def test_cli_local_profile_json_is_stdout_only_without_secrets(self):
        from nexus_harness.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))
            stdout = io.StringIO()
            stderr = io.StringIO()
            environ = {
                "POSTHOG_PERSONAL_API_KEY": SECRET,
                "GH_TOKEN": GITHUB_TOKEN,
                "GITHUB_TOKEN": GITHUB_TOKEN,
            }
            with (
                patch.dict(os.environ, environ, clear=False),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = main(
                    [
                        "--json",
                        "--project-root",
                        str(root),
                        "doctor",
                        "--profile",
                        "local",
                    ]
                )
            self.assertNotEqual(code, 2)
            self.assertEqual(stderr.getvalue().strip(), "")
            payload = json.loads(stdout.getvalue())
            self.assertIn("gate", payload)
            self.assertIn("checks", payload)
            blob = stdout.getvalue()
            self.assertNotIn(SECRET, blob)
            self.assertNotIn(GITHUB_TOKEN, blob)
            self.assertNotIn("phx_", blob)
            self.assertNotIn("ghp_", blob)

    def test_cli_ci_host_does_not_ssh(self):
        from nexus_harness.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_root(Path(tmp))

            def boom(*args, **kwargs):
                argv = args[0] if args else kwargs.get("args")
                raise AssertionError(f"unexpected process: {argv!r}")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch("subprocess.run", side_effect=boom),
                patch("subprocess.Popen", side_effect=boom),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = main(
                    [
                        "--json",
                        "--project-root",
                        str(root),
                        "doctor",
                        "--profile",
                        "ci-host",
                    ]
                )
            self.assertIn(code, (0, 1))
            payload = json.loads(stdout.getvalue())
            statuses = {item["name"]: item["status"] for item in payload["checks"]}
            self.assertEqual(statuses["ci-profile"], "ACTIVATION_REQUIRED")
            self.assertNotEqual(payload["gate"], "FAIL")


if __name__ == "__main__":
    unittest.main()
