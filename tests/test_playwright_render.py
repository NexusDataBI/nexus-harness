"""Playwright config renderer and hermetic capture — no browser download."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from nexus_harness.devserver import parse_frontend_section
from nexus_harness.evidence import read_evidence
from nexus_harness.playwright import (
    capture_route,
    render_playwright_config,
    validate_route,
)
from nexus_harness.safe import PathSafetyError
from nexus_harness.state import TaskState


REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE = REPO_ROOT / "src" / "nexus_harness" / "playwright.py"
TEMPLATE = REPO_ROOT / "templates" / "playwright" / "nexus.config.ts"
SCHEMA_PATH = REPO_ROOT / "core" / "ci" / "profile.schema.json"
BANNED_BASELINE_TOOLS = (
    "cypress",
    "percy",
    "chromatic",
    "selenium",
    "loki",
)


def _frontend(**overrides):
    data = {
        "base_url": "http://127.0.0.1:4173",
        "readiness_url": "http://127.0.0.1:4173",
        "visual_paths": ["apps/web/**"],
        "dev_server": {
            "command": ["npm", "run", "dev"],
            "timeout_seconds": 2,
        },
        "routes": [{"path": "/", "name": "home"}],
    }
    data.update(overrides)
    return data


def _config(**overrides):
    result = parse_frontend_section(_frontend(**overrides))
    if not result.ok or result.config is None:
        raise AssertionError(result.failure)
    return result.config


def _schema_object_ok(document, schema):
    required = set(schema.get("required", []))
    properties = set(schema.get("properties", {}))
    keys = set(document)
    return required <= keys and (
        schema.get("additionalProperties", True) or keys <= properties
    )


class PlaywrightRenderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_generated_config_uses_configured_base_url(self):
        path = render_playwright_config(_config(), artifact_root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:4173", text)
        self.assertIn("baseURL", text)

    def test_generated_config_defines_desktop_and_mobile_projects(self):
        path = render_playwright_config(_config(), artifact_root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("desktop", text)
        self.assertIn("mobile", text)
        self.assertIn("1280", text)
        self.assertIn("800", text)
        self.assertIn("390", text)
        self.assertIn("844", text)

    def test_generated_config_retains_trace_and_failure_screenshots(self):
        path = render_playwright_config(_config(), artifact_root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("on-first-retry", text)
        self.assertIn("only-on-failure", text)

    def test_generated_config_enables_screenshot_comparisons(self):
        path = render_playwright_config(_config(), artifact_root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("toHaveScreenshot", text)

    def test_video_is_off_by_default(self):
        path = render_playwright_config(_config(), artifact_root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("off", text)
        self.assertNotIn("retain-on-failure", text)

    def test_video_is_on_only_when_profile_opts_in(self):
        config = _config(playwright={"video": True})
        self.assertTrue(config.playwright.video)
        path = render_playwright_config(config, artifact_root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("retain-on-failure", text)

    def test_custom_viewports_override_defaults(self):
        config = _config(
            viewports=[
                {"name": "wide", "width": 1440, "height": 900},
                {"name": "narrow", "width": 360, "height": 640},
            ]
        )
        path = render_playwright_config(config, artifact_root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("wide", text)
        self.assertIn("narrow", text)
        self.assertIn("1440", text)
        self.assertIn("360", text)

    def test_output_dir_stays_inside_artifact_root(self):
        path = render_playwright_config(_config(), artifact_root=self.root)
        text = path.read_text(encoding="utf-8")
        resolved_root = str(self.root.resolve())
        self.assertTrue(str(path.resolve()).startswith(resolved_root))
        self.assertIn(resolved_root, text)

    def test_rejects_output_path_escaping_artifact_root(self):
        with self.assertRaises(PathSafetyError):
            render_playwright_config(
                _config(),
                artifact_root=self.root,
                output_relpath="../escape.config.ts",
            )

    def test_rejects_absolute_output_outside_artifact_root(self):
        with self.assertRaises(PathSafetyError):
            render_playwright_config(
                _config(),
                artifact_root=self.root,
                output_relpath="/tmp/nexus-playwright.config.ts",
            )

    def test_omitted_playwright_section_defaults_video_false(self):
        config = _config()
        self.assertFalse(config.playwright.video)
        self.assertEqual(config.viewports, ())

    def test_malformed_playwright_video_is_structured_failure(self):
        result = parse_frontend_section(_frontend(playwright={"video": "yes"}))
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "malformed_command")

    def test_malformed_viewport_is_structured_failure(self):
        result = parse_frontend_section(
            _frontend(viewports=[{"name": "desktop", "width": "wide", "height": 800}])
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "malformed_command")


class PlaywrightRouteTests(unittest.TestCase):
    def test_accepts_absolute_app_route(self):
        self.assertEqual(validate_route("/inbox"), "/inbox")
        self.assertEqual(validate_route("/"), "/")

    def test_rejects_relative_and_traversal_routes(self):
        for route in ("inbox", "../etc/passwd", "/ok/../secret"):
            with self.assertRaises(ValueError):
                validate_route(route)

    def test_rejects_scheme_and_backslash_routes(self):
        for route in ("https://evil.test/x", "/http://x", "/foo\\bar"):
            with self.assertRaises(ValueError):
                validate_route(route)


class PlaywrightCaptureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_capture_invokes_runner_with_argv_list_not_shell(self):
        seen: list[tuple[list[str], object]] = []

        def runner(argv, *, cwd=None):
            seen.append((list(argv), cwd))
            return 0, "", ""

        result = capture_route(
            "/settings",
            config=_config(),
            artifact_root=self.root,
            runner=runner,
            task_id="task-4",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(seen), 1)
        argv, _cwd = seen[0]
        self.assertIsInstance(argv, list)
        self.assertTrue(all(isinstance(part, str) for part in argv))
        self.assertIn("playwright", argv)
        self.assertIn("/settings", argv)
        self.assertNotIn("cypress", argv)
        self.assertFalse(
            any("&&" in part or ";" in part or "|" in part for part in argv)
        )
        self.assertFalse(any(part in {"-c", "-lc"} for part in argv))
        self.assertNotIn("playwright install", " ".join(argv))

    def test_capture_registers_evidence_with_exit_and_diff_hash(self):
        state = TaskState.new("task-4", "demo")
        state.current_diff_hash = "abc123def"

        def runner(argv, *, cwd=None):
            return 0, "", ""

        result = capture_route(
            "/inbox",
            config=_config(),
            artifact_root=self.root,
            runner=runner,
            task_id="task-4",
            task_state=state,
        )
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.evidence_path)
        records = read_evidence(result.evidence_path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].exit_code, 0)
        self.assertEqual(records[0].diff_hash, "abc123def")
        self.assertIn("playwright", records[0].command.lower())
        self.assertIsNotNone(records[0].artifact)
        artifact = Path(records[0].artifact)
        self.assertTrue(str(artifact.resolve()).startswith(str(self.root.resolve())))

    def test_capture_records_nonzero_exit_without_calling_real_npx(self):
        def runner(argv, *, cwd=None):
            self.assertNotIn("https://", " ".join(argv))
            return 1, "", "failed"

        result = capture_route(
            "/",
            config=_config(),
            artifact_root=self.root,
            runner=runner,
            task_id="task-4",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 1)
        records = read_evidence(result.evidence_path)
        self.assertEqual(records[0].exit_code, 1)

    def test_capture_rejects_unsafe_route_before_runner(self):
        runner = Mock(side_effect=AssertionError("runner must not run"))
        with self.assertRaises(ValueError):
            capture_route(
                "../escape",
                config=_config(),
                artifact_root=self.root,
                runner=runner,
            )
        runner.assert_not_called()


class PlaywrightBaselineTests(unittest.TestCase):
    def test_module_and_template_do_not_use_banned_baseline_tools(self):
        engine = ENGINE.read_text(encoding="utf-8")
        template = TEMPLATE.read_text(encoding="utf-8")
        for blob in (engine, template):
            lowered = blob.lower()
            for banned in BANNED_BASELINE_TOOLS:
                self.assertNotIn(banned, lowered)
        self.assertNotIn("playwright install", engine)
        self.assertNotIn("sdr-platform", engine.lower())
        self.assertNotIn("SDR-Plataform", engine)

    def test_engine_does_not_import_playwright_package(self):
        engine = ENGINE.read_text(encoding="utf-8")
        self.assertNotIn("from playwright", engine)
        self.assertNotIn("import playwright", engine)
        self.assertNotIn("playwright.sync_api", engine)

    def test_profile_schema_allows_optional_playwright_and_viewports(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        frontend = schema["properties"]["frontend"]
        self.assertIn("playwright", frontend["properties"])
        self.assertIn("viewports", frontend["properties"])
        self.assertNotIn("playwright", frontend.get("required", []))
        self.assertNotIn("viewports", frontend.get("required", []))
        self.assertFalse(frontend["properties"]["playwright"]["additionalProperties"])
        viewport = schema["$defs"]["frontendViewport"]
        self.assertFalse(viewport["additionalProperties"])
        self.assertEqual(set(viewport["required"]), {"name", "width", "height"})
        allowed = {
            "base_url": "http://127.0.0.1:3000",
            "readiness_url": "http://127.0.0.1:3000",
            "dev_server": {"command": ["npm", "run", "dev"]},
            "playwright": {"video": False},
            "viewports": [{"name": "desktop", "width": 1280, "height": 800}],
        }
        self.assertTrue(_schema_object_ok(allowed, frontend))
        extra = dict(allowed)
        extra["unexpected"] = True
        self.assertFalse(_schema_object_ok(extra, frontend))


if __name__ == "__main__":
    unittest.main()
