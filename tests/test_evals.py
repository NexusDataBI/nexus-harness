import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from nexus_harness.evals import load_cases, run_evals
from nexus_harness.__main__ import main

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "evals" / "cases"

REQUIRED_CASES = {
    "backend-bug",
    "frontend-feature",
    "multi-file-refactor",
    "database-migration",
    "auth-security",
    "long-horizon",
    "ambiguous-task",
    "production-deploy-dry-run",
}

EXTRA_CASES = {
    "memory-recall-freshness",
    "visual-stale-evidence",
    "runtime-incident-dedup",
    "github-bounded-bug-governance",
}


def _run_main(argv):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class EvalTests(unittest.TestCase):
    def test_required_eval_cases_exist(self):
        names = {case.name for case in load_cases(Path("evals/cases"))}
        required = {
            "backend-bug",
            "frontend-feature",
            "multi-file-refactor",
            "database-migration",
            "auth-security",
            "long-horizon",
            "ambiguous-task",
            "production-deploy-dry-run",
        }
        self.assertTrue(required.issubset(names))

    def test_representative_extra_cases_exist(self):
        names = {case.name for case in load_cases(CASES_DIR)}
        self.assertTrue(EXTRA_CASES.issubset(names), names)

    def test_cases_declare_required_expectation_fields(self):
        required_keys = {
            "classification",
            "tracking",
            "graph",
            "quality_profile",
            "approvals",
            "security",
            "completion",
            "ship",
            "forbidden",
        }
        for case in load_cases(CASES_DIR):
            with self.subTest(case=case.name):
                expect = case.expect
                missing = required_keys - set(expect)
                self.assertFalse(missing, f"{case.name} missing {sorted(missing)}")

    def test_production_deploy_case_requires_approval_and_digest(self):
        cases = {case.name: case for case in load_cases(CASES_DIR)}
        case = cases["production-deploy-dry-run"]
        approvals = case.expect["approvals"]
        self.assertTrue(approvals.get("required"))
        self.assertIn("production", approvals.get("required") or [])
        ship = case.expect["ship"]
        self.assertTrue(ship.get("requires_explicit_approval"))
        self.assertTrue(ship.get("requires_immutable_digest"))
        self.assertIn("mutable_latest_tag", case.expect["forbidden"])

    def test_deterministic_suite_passes_without_model_calls(self):
        report = run_evals(CASES_DIR)
        self.assertEqual(report.gate, "PASS", report.summary)
        names = {item.name for item in report.results}
        self.assertTrue(REQUIRED_CASES.issubset(names))
        for item in report.results:
            with self.subTest(case=item.name):
                self.assertEqual(item.status, "PASS", item.failures)
                self.assertEqual(item.model_eval, "SKIP")
                self.assertTrue(item.model_eval_reason)

    def test_runner_uses_real_tracking_and_hierarchy_policies(self):
        from nexus_harness.hierarchy import tracking_shape
        from nexus_harness.tracking import tracking_required

        cases = {case.name: case for case in load_cases(CASES_DIR)}
        bug = cases["backend-bug"]
        classified = bug.classification
        self.assertEqual(
            tracking_required(classified["work_type"], classified.get("mutable")),
            bug.expect["tracking"]["required"],
        )
        self.assertEqual(
            list(
                tracking_shape(
                    classified["scope"],
                    classified["work_type"],
                    independent_deliverables=classified.get("independent_deliverables"),
                )
            ),
            bug.expect["tracking"]["shape"],
        )
        long_horizon = cases["long-horizon"]
        self.assertEqual(
            list(
                tracking_shape(
                    long_horizon.classification["scope"],
                    long_horizon.classification["work_type"],
                )
            ),
            ["epic", "feature", "task"],
        )
        bounded = cases["github-bounded-bug-governance"]
        self.assertEqual(
            list(
                tracking_shape(
                    bounded.classification["scope"],
                    bounded.classification["work_type"],
                )
            ),
            ["bug"],
        )

    def test_runner_does_not_mutate_github(self):
        github = Mock()
        report = run_evals(CASES_DIR, github=github)
        self.assertEqual(report.gate, "PASS", report.summary)
        github.api_graphql.assert_not_called()
        github.create_issue.assert_not_called()
        github.edit_issue.assert_not_called()

    def test_failing_expectation_makes_eval_fail(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "broken-tracking",
                        "classification": {
                            "intent": "change",
                            "scope": "bounded",
                            "work_type": "bug",
                            "mutable": True,
                            "quality_profile": "standard",
                        },
                        "expect": {
                            "classification": {"work_type": "bug"},
                            "tracking": {"required": False, "shape": ["bug"]},
                            "graph": {"checks": []},
                            "quality_profile": {"name": "standard"},
                            "approvals": {"required": []},
                            "security": {},
                            "completion": {"status": "FAIL"},
                            "ship": {"ready": False},
                            "forbidden": ["remote_mutation"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            report = run_evals(Path(tmp))
        self.assertEqual(report.gate, "FAIL")
        self.assertTrue(any(item.status == "FAIL" for item in report.results))


class EvalCliTests(unittest.TestCase):
    def test_evals_run_exits_zero_on_pass(self):
        code, stdout, stderr = _run_main(
            ["--project-root", str(REPO_ROOT), "evals", "run"]
        )
        self.assertEqual(code, 0, stderr + stdout)
        self.assertRegex(stdout + stderr, r"\bPASS\b")

    def test_evals_run_json_has_no_secrets(self):
        code, stdout, stderr = _run_main(
            ["--json", "--project-root", str(REPO_ROOT), "evals", "run"]
        )
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["gate"], "PASS")
        self.assertEqual(stderr.strip(), "")
        self.assertNotIn("phx_", stdout)
        self.assertNotIn("ghp_", stdout)
        self.assertNotIn("github_pat_", stdout)
