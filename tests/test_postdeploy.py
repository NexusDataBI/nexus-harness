"""Post-deploy runtime verification — network-free tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from nexus_harness.postdeploy import (
    GATE_FAIL,
    GATE_INSUFFICIENT,
    GATE_PASS,
    evaluate_postdeploy,
)


FIXED = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


class PostDeployTests(unittest.TestCase):
    def test_new_release_error_regression_fails_verification(self):
        result = evaluate_postdeploy(health=True, smoke=True, new_error_regression=True)
        self.assertEqual(result.gate, GATE_FAIL)
        self.assertEqual(result.rollback_handoff, "signal")

    def test_health_fail_is_fail(self):
        result = evaluate_postdeploy(
            health=False, smoke=True, new_error_regression=False
        )
        self.assertEqual(result.gate, GATE_FAIL)

    def test_smoke_fail_is_fail(self):
        result = evaluate_postdeploy(
            health=True, smoke=False, new_error_regression=False
        )
        self.assertEqual(result.gate, GATE_FAIL)

    def test_health_smoke_pass_without_enough_telemetry_is_insufficient(self):
        result = evaluate_postdeploy(
            health=True,
            smoke=True,
            new_error_regression=False,
            observations_available=0,
            minimum_sample=5,
            window_start=FIXED,
            window_end=FIXED,
        )
        self.assertEqual(result.gate, GATE_INSUFFICIENT)
        self.assertNotEqual(result.gate, GATE_PASS)
        self.assertNotEqual(result.gate, GATE_FAIL)
        self.assertIsNone(result.rollback_handoff)

    def test_no_events_is_not_pass(self):
        result = evaluate_postdeploy(
            health=True,
            smoke=True,
            new_error_regression=False,
            observations_available=0,
        )
        self.assertEqual(result.gate, GATE_INSUFFICIENT)

    def test_sufficient_clean_telemetry_is_pass(self):
        result = evaluate_postdeploy(
            health=True,
            smoke=True,
            new_error_regression=False,
            observations_available=12,
            minimum_sample=5,
            window_start=FIXED,
            window_end=FIXED,
        )
        self.assertEqual(result.gate, GATE_PASS)
        self.assertIsNone(result.rollback_handoff)

    def test_insufficient_does_not_close_issue(self):
        result = evaluate_postdeploy(
            health=True,
            smoke=True,
            new_error_regression=False,
            observations_available=1,
            minimum_sample=10,
        )
        self.assertFalse(result.issue_close_eligible)


if __name__ == "__main__":
    unittest.main()
