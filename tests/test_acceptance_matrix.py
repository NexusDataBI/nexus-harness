"""Spec §22 acceptance matrix — every criterion must have concrete evidence."""

from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

from nexus_harness.acceptance import (
    ALLOWED_STATES,
    EVIDENCE_KINDS,
    LIVE_ONLY_IDS,
    SPEC_STATEMENTS,
    SUCCESS_CRITERIA,
    Criterion,
    Evidence,
    evaluate_matrix,
)
from nexus_harness.doctor import run_doctor
from nexus_harness.evals import run_evals
from nexus_harness.validate import validate_repository

REPO_ROOT = Path(__file__).resolve().parents[1]


class AcceptanceMatrixTests(unittest.TestCase):
    def test_matrix_covers_all_twenty_spec_criteria(self):
        self.assertEqual(len(SUCCESS_CRITERIA), 20)
        self.assertEqual(len(SPEC_STATEMENTS), 20)
        ids = [item.id for item in SUCCESS_CRITERIA]
        self.assertEqual(ids, list(range(1, 21)))
        for item, statement in zip(SUCCESS_CRITERIA, SPEC_STATEMENTS, strict=True):
            self.assertEqual(item.statement, statement)

    def test_every_criterion_has_allowed_state_and_evidence_kind(self):
        for item in SUCCESS_CRITERIA:
            with self.subTest(id=item.id):
                self.assertIn(item.expected_status, ALLOWED_STATES)
                self.assertTrue(item.evidence, f"criterion {item.id} has no evidence")
                for ev in item.evidence:
                    self.assertIn(ev.kind, EVIDENCE_KINDS)
                    self.assertTrue(ev.path, f"criterion {item.id} evidence path empty")

    def test_live_only_criteria_are_activation_required_not_pass(self):
        self.assertEqual(LIVE_ONLY_IDS, frozenset({15, 18, 19}))
        for item in SUCCESS_CRITERIA:
            if item.id in LIVE_ONLY_IDS:
                self.assertTrue(item.live)
                self.assertEqual(item.expected_status, "ACTIVATION_REQUIRED")
            else:
                self.assertFalse(item.live)
                self.assertEqual(item.expected_status, "PASS")

    def test_matrix_fails_when_a_criterion_lacks_evidence(self):
        broken = Criterion(
            id=99,
            statement="synthetic row used to prove the evidence gate",
            expected_status="PASS",
            live=False,
            evidence=(),
        )
        report = evaluate_matrix(REPO_ROOT, criteria=(broken,))
        self.assertEqual(report.gate, "FAIL")
        self.assertEqual(report.fail_count, 1)
        self.assertTrue(report.results[0].missing)

    def test_evaluate_matrix_proves_evidence_files_and_selectors(self):
        report = evaluate_matrix(REPO_ROOT)
        self.assertEqual(len(report.results), 20)
        self.assertEqual(report.fail_count, 0, report.summary)
        self.assertEqual(report.gate, "PASS")
        self.assertEqual(
            tuple(item.id for item in report.results if item.live), (15, 18, 19)
        )
        for result in report.results:
            with self.subTest(id=result.id):
                self.assertEqual(result.missing, ())
                self.assertEqual(result.status, result.expected_status)

    def test_local_release_gate_rejects_fake_live_pass(self):
        fake_live_pass = Criterion(
            id=15,
            statement=SPEC_STATEMENTS[14],
            expected_status="PASS",
            live=True,
            evidence=(
                Evidence(
                    kind="unit_test",
                    path="tests/test_ci_vps_files.py",
                    selector="test_required_files_exist",
                ),
            ),
        )
        report = evaluate_matrix(REPO_ROOT, criteria=(fake_live_pass,))
        self.assertEqual(report.gate, "FAIL")
        self.assertEqual(report.results[0].status, "FAIL")

    def test_canonical_skills_and_validator_evidence_is_live(self):
        skills = {
            path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")
        }
        self.assertEqual(
            skills,
            {
                "accessibility",
                "nexus-frontend",
                "nexus-handoff",
                "nexus-quality",
                "nexus-ship",
                "nexus-verify",
                "nexus-workflow",
            },
        )
        result = validate_repository(REPO_ROOT)
        self.assertEqual(result.errors, ())

    def test_evals_and_doctor_do_not_claim_live_saas_pass(self):
        evals = run_evals(REPO_ROOT / "evals" / "cases")
        self.assertEqual(evals.gate, "PASS", evals.summary)
        doctor = run_doctor(REPO_ROOT, profile="ci-host", environ={})
        by_name = {check.name: check for check in doctor.checks}
        self.assertEqual(by_name["ci-profile"].status, "ACTIVATION_REQUIRED")
        self.assertEqual(by_name["github"].status, "ACTIVATION_REQUIRED")
        self.assertIn(by_name["posthog"].status, {"SKIP", "ACTIVATION_REQUIRED"})
        self.assertNotEqual(by_name["ci-profile"].status, "PASS")
        self.assertNotEqual(by_name["github"].status, "PASS")
        self.assertNotEqual(by_name["posthog"].status, "PASS")

    def test_generated_adapter_configs_parse(self):
        from nexus_harness.adapters import render_all

        files = {item.relative_path: item.content for item in render_all(REPO_ROOT)}
        settings = json.loads(files["claude/settings.json"])
        sandbox = json.loads(files["cursor/sandbox.json"])
        config = tomllib.loads(files["codex/config.toml"].decode("utf-8"))
        self.assertIn("hooks", settings)
        self.assertEqual(sandbox["type"], "workspace_readwrite")
        self.assertNotIn("disabled", sandbox)
        self.assertIn("sandbox_mode", config)


if __name__ == "__main__":
    unittest.main()
