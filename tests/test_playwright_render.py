"""Playwright config renderer and hermetic capture — no browser download."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from nexus_harness.completion import evaluate_completion
from nexus_harness.devserver import parse_frontend_section
from nexus_harness.evidence import read_evidence
from nexus_harness.playwright import (
    PlaywrightError,
    build_capture_argv,
    capture_route,
    render_playwright_config,
    validate_route,
)
from nexus_harness.safe import PathSafetyError
from nexus_harness.state import TaskState
from nexus_harness.visual import as_visual_evidence, visual_completion_reasons


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
                {"name": "desktop", "width": 1440, "height": 900},
                {"name": "mobile", "width": 360, "height": 640},
            ]
        )
        path = render_playwright_config(config, artifact_root=self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("desktop", text)
        self.assertIn("mobile", text)
        self.assertIn("1440", text)
        self.assertIn("360", text)
        self.assertNotIn("wide", text)
        self.assertNotIn("narrow", text)

    def test_rejects_viewport_names_outside_closed_set(self):
        result = parse_frontend_section(
            _frontend(
                viewports=[
                    {"name": "wide", "width": 1440, "height": 900},
                    {"name": "narrow", "width": 360, "height": 640},
                ]
            )
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "malformed_command")

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
        self.assertEqual(validate_route("/dashboard"), "/dashboard")
        self.assertEqual(validate_route("/foo/bar"), "/foo/bar")

    def test_rejects_relative_and_traversal_routes(self):
        for route in ("inbox", "../etc/passwd", "/ok/../secret"):
            with self.assertRaises(ValueError):
                validate_route(route)

    def test_rejects_scheme_and_backslash_routes(self):
        for route in ("https://evil.test/x", "/http://x", "/foo\\bar"):
            with self.assertRaises(ValueError):
                validate_route(route)

    def test_rejects_protocol_relative_routes(self):
        for route in ("//evil.test", "///evil.test", "//evil.test/path"):
            with self.assertRaises(PlaywrightError):
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

    def test_capture_rejects_protocol_relative_route_before_runner(self):
        runner = Mock(side_effect=AssertionError("runner must not run"))
        with self.assertRaises(PlaywrightError):
            capture_route(
                "//evil.test",
                config=_config(),
                artifact_root=self.root,
                runner=runner,
            )
        runner.assert_not_called()

    def test_capture_escapes_route_for_playwright_grep(self):
        route = "/inbox(.*)"
        argv = build_capture_argv(
            config_path=self.root / "playwright" / "nexus.config.ts",
            spec_path=self.root / "playwright" / "capture.spec.ts",
            output_dir=self.root / "playwright" / "output",
            route=route,
        )
        grep_at = argv.index("--grep")
        self.assertEqual(argv[grep_at + 1], re.escape(route))
        self.assertNotEqual(argv[grep_at + 1], route)
        self.assertIn("--update-snapshots", argv)

    def test_generated_spec_listens_for_console_and_failed_requests(self):
        def runner(argv, *, cwd=None):
            return 0, "", ""

        result = capture_route(
            "/inbox",
            config=_config(),
            artifact_root=self.root,
            runner=runner,
        )
        self.assertIsNotNone(result.spec_path)
        text = result.spec_path.read_text(encoding="utf-8")
        self.assertRegex(text, r"page\.on\(\s*['\"]console['\"]")
        self.assertIn("requestfailed", text)

    def test_capture_writes_visual_evidence_for_required_viewports(self):
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
        self.assertEqual(len(state.visual_evidence), 2)
        records = [as_visual_evidence(item) for item in state.visual_evidence]
        self.assertTrue(all(record is not None for record in records))
        viewports = {record.viewport for record in records}
        self.assertEqual(viewports, {"desktop", "mobile"})
        root = self.root.resolve()
        for record in records:
            self.assertEqual(record.diff_hash, "abc123def")
            self.assertEqual(record.route, "/inbox")
            self.assertEqual(record.console_error_count, 0)
            self.assertEqual(record.failed_request_count, 0)
            screenshot = Path(record.screenshot)
            self.assertTrue(screenshot.is_file())
            self.assertTrue(screenshot.resolve().is_relative_to(root))

    def test_capture_reads_sidecar_console_and_network_counts(self):
        state = TaskState.new("task-4", "demo")
        state.current_diff_hash = "abc123def"

        def runner(argv, *, cwd=None):
            output = self.root / "playwright" / "output"
            output.mkdir(parents=True, exist_ok=True)
            (output / "desktop-runtime.json").write_text(
                json.dumps({"console_error_count": 2, "failed_request_count": 1}),
                encoding="utf-8",
            )
            (output / "mobile-runtime.json").write_text(
                json.dumps({"console_error_count": 0, "failed_request_count": 0}),
                encoding="utf-8",
            )
            return 0, "", ""

        capture_route(
            "/inbox",
            config=_config(),
            artifact_root=self.root,
            runner=runner,
            task_state=state,
        )
        by_viewport = {
            as_visual_evidence(item).viewport: as_visual_evidence(item)
            for item in state.visual_evidence
        }
        self.assertEqual(by_viewport["desktop"].console_error_count, 2)
        self.assertEqual(by_viewport["desktop"].failed_request_count, 1)
        self.assertEqual(by_viewport["mobile"].console_error_count, 0)

    def test_failed_capture_does_not_promote_visual_evidence(self):
        state = TaskState.new("task-4", "demo")
        state.current_diff_hash = "abc"
        state.visual_required = True

        def runner(argv, *, cwd=None):
            return 1, "", "failed"

        result = capture_route(
            "/",
            config=_config(),
            artifact_root=self.root,
            runner=runner,
            task_state=state,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.visual_evidence, ())
        self.assertFalse(
            any(
                as_visual_evidence(item) is not None
                and as_visual_evidence(item).screenshot
                for item in state.visual_evidence
            )
        )
        output = self.root / "playwright" / "output"
        self.assertFalse((output / "desktop-after.png").is_file())
        self.assertFalse((output / "mobile-after.png").is_file())
        reasons = visual_completion_reasons(state, "abc")
        self.assertTrue(reasons)
        self.assertTrue(
            any("desktop" in reason or "mobile" in reason for reason in reasons)
        )
        completion = evaluate_completion(
            {
                "tracking_required": True,
                "issue": 123,
                "acceptance": [{"id": "AC-1", "status": "PASS", "evidence": "ev-1"}],
                "quality_gate": {
                    "gate": "PASS",
                    "diff_hash": "abc",
                    "report": "structured",
                },
                "security_gate": {
                    "gate": "PASS",
                    "diff_hash": "abc",
                    "report": "structured",
                },
                "review_gate": "PASS",
                "current_diff_hash": "abc",
                "verified_diff_hash": "abc",
                "reviewed_diff_hash": "abc",
                "evidence": [{"id": "ev-1", "exit_code": 0, "diff_hash": "abc"}],
                "findings": [],
                "visual_required": True,
                "visual_evidence": list(state.visual_evidence),
            }
        )
        self.assertEqual(completion.status, "FAIL")
        self.assertTrue(
            any(
                "visual" in reason or "desktop" in reason or "mobile" in reason
                for reason in completion.reasons
            )
        )


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
