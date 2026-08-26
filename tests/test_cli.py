"""CLI entrypoint tests — python3 -m nexus_harness (no real docker/git required)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nexus_harness.__main__ import main

REPO_ROOT = Path(__file__).resolve().parents[1]
SDR_PROFILE = REPO_ROOT / "profiles" / "projects" / "sdr-platform.toml"


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


if __name__ == "__main__":
    unittest.main()
