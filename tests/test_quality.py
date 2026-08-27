import unittest

from nexus_harness.quality import (
    Metric,
    evaluate_metric,
    evaluate_report,
    load_quality_profile,
    validate_baseline_change,
)


class QualityTests(unittest.TestCase):
    def test_lower_is_better_ratchet_rejects_regression(self):
        metric = Metric(
            "lint_warnings", current=13, baseline=12, mode="ratchet", direction="lower"
        )
        self.assertEqual(evaluate_metric(metric).status, "FAIL")

    def test_higher_is_better_ratchet_accepts_improvement(self):
        metric = Metric(
            "coverage", current=81.0, baseline=80.0, mode="ratchet", direction="higher"
        )
        self.assertEqual(evaluate_metric(metric).status, "PASS")

    def test_higher_is_better_ratchet_rejects_regression(self):
        metric = Metric(
            "coverage", current=79.0, baseline=80.0, mode="ratchet", direction="higher"
        )
        self.assertEqual(evaluate_metric(metric).status, "FAIL")

    def test_lower_is_better_ratchet_accepts_improvement(self):
        metric = Metric(
            "lint_warnings", current=10, baseline=12, mode="ratchet", direction="lower"
        )
        self.assertEqual(evaluate_metric(metric).status, "PASS")

    def test_ratchet_maintains_equal_baseline(self):
        higher = Metric(
            "coverage", current=80.0, baseline=80.0, mode="ratchet", direction="higher"
        )
        lower = Metric(
            "lint_warnings", current=12, baseline=12, mode="ratchet", direction="lower"
        )
        self.assertEqual(evaluate_metric(higher).status, "PASS")
        self.assertEqual(evaluate_metric(lower).status, "PASS")

    def test_absolute_lower_rejects_above_threshold(self):
        metric = Metric(
            "failing_tests", current=1, threshold=0, mode="absolute", direction="lower"
        )
        self.assertEqual(evaluate_metric(metric).status, "FAIL")

    def test_absolute_lower_accepts_at_threshold(self):
        metric = Metric(
            "failing_tests", current=0, threshold=0, mode="absolute", direction="lower"
        )
        self.assertEqual(evaluate_metric(metric).status, "PASS")

    def test_absolute_higher_requires_threshold(self):
        metric = Metric(
            "coverage",
            current=81.0,
            threshold=80.0,
            mode="absolute",
            direction="higher",
        )
        self.assertEqual(evaluate_metric(metric).status, "PASS")
        metric = Metric(
            "coverage",
            current=79.0,
            threshold=80.0,
            mode="absolute",
            direction="higher",
        )
        self.assertEqual(evaluate_metric(metric).status, "FAIL")

    def test_budget_allows_regression_within_tolerance(self):
        metric = Metric(
            "performance",
            current=105.0,
            baseline=100.0,
            mode="budget",
            direction="lower",
            tolerance=10.0,
        )
        self.assertEqual(evaluate_metric(metric).status, "PASS")

    def test_budget_rejects_regression_beyond_tolerance(self):
        metric = Metric(
            "performance",
            current=120.0,
            baseline=100.0,
            mode="budget",
            direction="lower",
            tolerance=10.0,
        )
        self.assertEqual(evaluate_metric(metric).status, "FAIL")

    def test_required_metric_failure_overrides_high_aggregate_score(self):
        report = evaluate_report(
            [
                Metric(
                    "coverage",
                    current=99.0,
                    baseline=80.0,
                    mode="ratchet",
                    direction="higher",
                    required=True,
                ),
                Metric(
                    "failing_tests",
                    current=1,
                    threshold=0,
                    mode="absolute",
                    direction="lower",
                    required=True,
                ),
            ],
            score=0.99,
        )
        self.assertGreaterEqual(report.score, 0.99)
        self.assertEqual(report.gate, "FAIL")

    def test_optional_metric_failure_does_not_fail_gate(self):
        report = evaluate_report(
            [
                Metric(
                    "coverage",
                    current=81.0,
                    baseline=80.0,
                    mode="ratchet",
                    direction="higher",
                    required=True,
                ),
                Metric(
                    "duplication",
                    current=9,
                    baseline=8,
                    mode="ratchet",
                    direction="lower",
                    required=False,
                ),
            ],
            score=0.5,
        )
        self.assertEqual(report.gate, "PASS")

    def test_agent_cannot_weaken_coverage_baseline_to_pass(self):
        base = {"coverage": 80.0, "lint_warnings": 12}
        proposed = {"coverage": 70.0, "lint_warnings": 12}
        measured = {"coverage": 70.0, "lint_warnings": 12}
        with self.assertRaises(ValueError):
            validate_baseline_change(base, proposed, measured)

    def test_agent_cannot_increase_lint_warning_baseline_to_pass(self):
        base = {"coverage": 80.0, "lint_warnings": 12}
        proposed = {"coverage": 80.0, "lint_warnings": 20}
        measured = {"coverage": 80.0, "lint_warnings": 20}
        with self.assertRaises(ValueError):
            validate_baseline_change(base, proposed, measured)

    def test_proposed_direction_cannot_flip_coverage_ratchet(self):
        base = {"coverage": 80}
        proposed = {"coverage": {"value": 70, "direction": "lower"}}
        measured = {"coverage": 70}
        with self.assertRaises(ValueError):
            validate_baseline_change(base, proposed, measured)

    def test_proposed_direction_cannot_flip_lint_warning_ratchet(self):
        base = {"lint_warnings": 12}
        proposed = {"lint_warnings": {"value": 20, "direction": "higher"}}
        measured = {"lint_warnings": 20}
        with self.assertRaises(ValueError):
            validate_baseline_change(base, proposed, measured)

    def test_proposed_direction_flip_is_rejected_even_for_better_value(self):
        base = {"coverage": 80}
        proposed = {"coverage": {"value": 85, "direction": "lower"}}
        measured = {"coverage": 85}
        with self.assertRaises(ValueError):
            validate_baseline_change(base, proposed, measured)

    def test_existing_base_direction_governs_custom_metric(self):
        base = {"custom_metric": {"value": 80, "direction": "higher"}}
        proposed = {"custom_metric": {"value": 70, "direction": "lower"}}
        measured = {"custom_metric": 70}
        with self.assertRaises(ValueError):
            validate_baseline_change(base, proposed, measured, policy={"precision": {}})

    def test_stale_baseline_rejected_when_improvement_must_be_promoted(self):
        base = {"coverage": 80.0, "lint_warnings": 12}
        proposed = {"coverage": 80.0, "lint_warnings": 12}
        measured = {"coverage": 81.0, "lint_warnings": 10}
        with self.assertRaises(ValueError):
            validate_baseline_change(base, proposed, measured)

    def test_promotion_must_equal_measured_improvement_within_precision(self):
        base = {"coverage": 80.0}
        proposed = {"coverage": 81.0}
        measured = {"coverage": 81.004}
        validate_baseline_change(base, proposed, measured)

    def test_light_profile_excludes_coverage_standard_includes_it(self):
        light = load_quality_profile("light")
        standard = load_quality_profile("standard")
        self.assertFalse(light["coverage"])
        self.assertTrue(standard["coverage"])
        self.assertTrue(light["format_lint"])
        self.assertTrue(standard["security_scan"])

    def test_required_ratchet_without_baseline_is_bootstrap_required(self):
        metric = Metric(
            "coverage",
            current=81.0,
            baseline=None,
            mode="ratchet",
            direction="higher",
            required=True,
        )
        result = evaluate_metric(metric)
        self.assertEqual(result.status, "BOOTSTRAP_REQUIRED")
        self.assertNotEqual(result.status, "PASS")

    def test_required_budget_without_baseline_is_bootstrap_required(self):
        metric = Metric(
            "performance",
            current=100.0,
            baseline=None,
            mode="budget",
            direction="lower",
            required=True,
        )
        result = evaluate_metric(metric)
        self.assertEqual(result.status, "BOOTSTRAP_REQUIRED")

    def test_optional_ratchet_without_baseline_is_not_applicable(self):
        metric = Metric(
            "duplication",
            current=8,
            baseline=None,
            mode="ratchet",
            direction="lower",
            required=False,
        )
        result = evaluate_metric(metric)
        self.assertEqual(result.status, "NOT_APPLICABLE")

    def test_budget_uses_policy_default_tolerance_when_unset(self):
        metric = Metric(
            "performance",
            current=105.0,
            baseline=100.0,
            mode="budget",
            direction="lower",
        )
        policy = {"budget": {"default_tolerance": 10.0}}
        self.assertEqual(evaluate_metric(metric, policy=policy).status, "PASS")
        tight = {"budget": {"default_tolerance": 0.0}}
        self.assertEqual(evaluate_metric(metric, policy=tight).status, "FAIL")

    def test_required_bootstrap_metric_does_not_pass_the_gate(self):
        report = evaluate_report(
            [
                Metric(
                    "coverage",
                    current=99.0,
                    baseline=None,
                    mode="ratchet",
                    direction="higher",
                    required=True,
                )
            ]
        )
        self.assertEqual(report.metrics[0].status, "BOOTSTRAP_REQUIRED")
        self.assertNotEqual(report.gate, "PASS")


if __name__ == "__main__":
    unittest.main()
