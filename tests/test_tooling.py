import json
import tempfile
import unittest
from pathlib import Path

from nexus_harness.tooling import (
    BASELINE_TOOLS,
    STATUS_BASELINE,
    STATUS_CONFLICT,
    STATUS_EXISTING,
    STATUS_MIGRATION_RECOMMENDED,
    bootstrap_guidance,
    detect_package_manager,
    detect_tools,
    load_tooling_policy,
    run_quality,
)


class ToolingTests(unittest.TestCase):
    def test_baseline_has_one_tool_per_role(self):
        self.assertEqual(BASELINE_TOOLS["lint"], "biome")
        self.assertEqual(BASELINE_TOOLS["unit_integration"], "vitest")
        self.assertEqual(BASELINE_TOOLS["e2e_visual"], "playwright")
        self.assertEqual(BASELINE_TOOLS["security"], "trivy")

    def test_policy_loads_existing_tooling_toml(self):
        policy = load_tooling_policy()
        self.assertTrue(policy["one_primary_tool_per_responsibility"])
        self.assertEqual(policy["baseline"]["format_lint"], "biome")
        self.assertEqual(policy["baseline"]["unit_integration"], "vitest")
        self.assertEqual(policy["baseline"]["e2e_visual"], "playwright")
        self.assertEqual(policy["baseline"]["security"], "trivy")
        not_baseline = set(policy["not_baseline"]["tools"])
        for forbidden in (
            "sentry",
            "datadog",
            "codecov",
            "semgrep",
            "gitleaks",
            "knip",
            "stryker",
        ):
            self.assertIn(forbidden, not_baseline)
        self.assertNotIn("biome", not_baseline)

    def test_detects_package_manager_from_lockfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pnpm-lock.yaml").write_text(
                "lockfileVersion: 9\n", encoding="utf-8"
            )
            self.assertEqual(detect_package_manager(root), "pnpm")
            (root / "pnpm-lock.yaml").unlink()
            (root / "package-lock.json").write_text("{}", encoding="utf-8")
            self.assertEqual(detect_package_manager(root), "npm")

    def test_greenfield_bootstrap_installs_only_biome_vitest_playwright(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps({"name": "fresh", "devDependencies": {}}),
                encoding="utf-8",
            )
            (root / "package-lock.json").write_text("{}", encoding="utf-8")
            plan = bootstrap_guidance(root)
            self.assertEqual(plan.package_manager, "npm")
            by_role = {item.role: item for item in plan.detections}
            self.assertEqual(by_role["lint"].status, STATUS_BASELINE)
            self.assertEqual(by_role["unit_integration"].status, STATUS_BASELINE)
            self.assertEqual(by_role["e2e_visual"].status, STATUS_BASELINE)
            self.assertEqual(by_role["security"].status, STATUS_BASELINE)
            self.assertEqual(
                set(plan.install_dev_deps),
                {"@biomejs/biome", "vitest", "@playwright/test"},
            )
            self.assertEqual(plan.expect_host_tools, ("trivy",))
            self.assertNotIn("eslint", plan.install_dev_deps)
            self.assertNotIn("jest", plan.install_dev_deps)
            self.assertNotIn("cypress", plan.install_dev_deps)

    def test_existing_baseline_tools_report_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "devDependencies": {
                            "@biomejs/biome": "1.0.0",
                            "vitest": "2.0.0",
                            "@playwright/test": "1.0.0",
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "biome.json").write_text("{}", encoding="utf-8")
            plan = detect_tools(root)
            by_role = {item.role: item for item in plan.detections}
            self.assertEqual(by_role["lint"].status, STATUS_EXISTING)
            self.assertEqual(by_role["unit_integration"].status, STATUS_EXISTING)
            self.assertEqual(by_role["e2e_visual"].status, STATUS_EXISTING)
            self.assertEqual(plan.install_dev_deps, ())

    def test_eslint_jest_cypress_recommend_migration_not_blind_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "devDependencies": {
                            "eslint": "9.0.0",
                            "jest": "29.0.0",
                            "cypress": "13.0.0",
                        }
                    }
                ),
                encoding="utf-8",
            )
            plan = detect_tools(root)
            by_role = {item.role: item for item in plan.detections}
            self.assertEqual(by_role["lint"].status, STATUS_MIGRATION_RECOMMENDED)
            self.assertEqual(
                by_role["unit_integration"].status, STATUS_MIGRATION_RECOMMENDED
            )
            self.assertEqual(by_role["e2e_visual"].status, STATUS_MIGRATION_RECOMMENDED)
            self.assertEqual(plan.install_dev_deps, ())
            self.assertIn("eslint", by_role["lint"].found)
            self.assertIn("jest", by_role["unit_integration"].found)
            self.assertIn("cypress", by_role["e2e_visual"].found)

    def test_overlapping_biome_and_eslint_is_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "devDependencies": {
                            "@biomejs/biome": "1.0.0",
                            "eslint": "9.0.0",
                        }
                    }
                ),
                encoding="utf-8",
            )
            plan = detect_tools(root)
            lint = next(item for item in plan.detections if item.role == "lint")
            self.assertEqual(lint.status, STATUS_CONFLICT)
            self.assertEqual(plan.install_dev_deps, ())

    def test_run_quality_standard_orchestrates_and_normalizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "scripts": {"typecheck": "tsc --noEmit"},
                        "devDependencies": {
                            "@biomejs/biome": "1.0.0",
                            "vitest": "2.0.0",
                            "typescript": "5.0.0",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "package-lock.json").write_text("{}", encoding="utf-8")

            calls: list[tuple[str, ...]] = []

            def fake_runner(argv, *, cwd):
                calls.append(tuple(argv))
                tool = argv[0]
                if tool in {"npx", "npm"} and "biome" in argv:
                    return 0, json.dumps({"summary": {"diagnostics": {"warn": 0}}}), ""
                if tool in {"npx", "npm"} and "vitest" in argv:
                    return (
                        0,
                        json.dumps(
                            {
                                "numFailedTests": 0,
                                "numPassedTests": 3,
                                "coverage": {"lines": {"pct": 82.0}},
                            }
                        ),
                        "",
                    )
                if tool in {"npx", "npm"} and ("tsc" in argv or "typecheck" in argv):
                    return 0, "", ""
                if tool == "trivy":
                    return (
                        0,
                        json.dumps(
                            {
                                "Results": [
                                    {
                                        "Target": "package-lock.json",
                                        "Vulnerabilities": [],
                                    }
                                ]
                            }
                        ),
                        "",
                    )
                raise AssertionError(f"unexpected command: {argv}")

            result = run_quality(
                profile="standard",
                project_root=root,
                runner=fake_runner,
                baselines={"coverage": 80.0, "lint_warnings": 0},
            )
            self.assertEqual(result.quality.gate, "PASS")
            self.assertEqual(result.security.gate, "PASS")
            self.assertEqual(result.security.scanner, "trivy")
            joined = [" ".join(c) for c in calls]
            self.assertTrue(any("biome" in line for line in joined))
            self.assertTrue(any("vitest" in line for line in joined))
            self.assertTrue(any("trivy" in line for line in joined))
            self.assertFalse(any("playwright" in line for line in joined))
            self.assertFalse(any("codecov" in line for line in joined))

    def test_run_quality_runs_playwright_when_affected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "devDependencies": {
                            "@biomejs/biome": "1.0.0",
                            "vitest": "2.0.0",
                            "@playwright/test": "1.0.0",
                        }
                    }
                ),
                encoding="utf-8",
            )

            calls: list[tuple[str, ...]] = []

            def fake_runner(argv, *, cwd):
                calls.append(tuple(argv))
                if "playwright" in argv:
                    return 0, json.dumps({"suites": []}), ""
                if "biome" in argv:
                    return 0, "{}", ""
                if "vitest" in argv:
                    return (
                        0,
                        json.dumps(
                            {
                                "numFailedTests": 0,
                                "numPassedTests": 1,
                                "coverage": {"lines": {"pct": 90.0}},
                            }
                        ),
                        "",
                    )
                if argv[0] == "trivy":
                    return 0, json.dumps({"Results": []}), ""
                return 0, "", ""

            result = run_quality(
                profile="standard",
                affected={"checks": ["web-test", "playwright"]},
                project_root=root,
                runner=fake_runner,
                baselines={"coverage": 80.0, "lint_warnings": 0},
            )
            self.assertEqual(result.quality.gate, "PASS")
            self.assertTrue(any("playwright" in " ".join(c) for c in calls))

    def test_run_quality_empty_affected_is_pass_without_running(self):
        calls: list[tuple[str, ...]] = []

        def fake_runner(argv, *, cwd):
            calls.append(tuple(argv))
            return 0, "", ""

        result = run_quality(
            profile="standard",
            affected={"components": [], "checks": [], "images": []},
            project_root=Path("."),
            runner=fake_runner,
        )
        self.assertEqual(result.quality.gate, "PASS")
        self.assertEqual(calls, [])
        self.assertIsNone(result.security)
