"""CI-host health summary and CI budget report."""

from __future__ import annotations

import unittest

from nexus_harness.graph import GraphNode
from nexus_harness.infra import (
    DEFAULT_TARGET_GITHUB_HOSTED_MINUTES,
    estimate_ci_budget,
    format_ci_budget_report,
    summarize_health,
    target_github_hosted_minutes,
)


class InfraTests(unittest.TestCase):
    def test_failed_disk_threshold_blocks_ci_host(self):
        report = summarize_health({"disk_percent": 96, "runner": True, "docker": True})
        self.assertEqual(report.gate, "FAIL")

    def test_disk_warn_threshold(self):
        report = summarize_health({"disk_percent": 86, "runner": True, "docker": True})
        self.assertEqual(report.gate, "WARN")

    def test_healthy_host_passes(self):
        report = summarize_health(
            {
                "disk_percent": 40,
                "memory_percent": 50,
                "runner": True,
                "docker": True,
                "cache_writable": True,
                "clock_skew_seconds": 1,
                "required_directories": {"cache": True, "artifacts": True},
                "tools": {"docker": True, "git": True},
            }
        )
        self.assertEqual(report.gate, "PASS")

    def test_missing_runner_or_cache_fails(self):
        report = summarize_health(
            {
                "disk_percent": 10,
                "runner": False,
                "docker": True,
                "cache_writable": False,
            }
        )
        self.assertEqual(report.gate, "FAIL")
        names = {c.name: c.status for c in report.checks}
        self.assertEqual(names["runner"], "FAIL")
        self.assertEqual(names["cache_writable"], "FAIL")

    def test_budget_default_target_is_zero_github_hosted(self):
        self.assertEqual(DEFAULT_TARGET_GITHUB_HOSTED_MINUTES, 0.0)
        self.assertEqual(target_github_hosted_minutes(), 0.0)

    def test_budget_from_graph_nodes(self):
        nodes = [
            GraphNode(id="a", execution_target="self_hosted", estimated_cost=12.5),
            GraphNode(id="b", execution_target="self_hosted", estimated_cost=7.5),
            GraphNode(id="c", execution_target="github_hosted", estimated_cost=3.0),
            GraphNode(id="d", execution_target="local", estimated_cost=99.0),
        ]
        report = estimate_ci_budget(nodes)
        self.assertEqual(report.self_hosted_cpu_minutes, 20.0)
        self.assertEqual(report.github_hosted_minutes, 3.0)
        self.assertEqual(report.target_github_hosted_minutes, 0.0)
        self.assertFalse(report.within_policy)
        text = format_ci_budget_report(report)
        self.assertIn("self_hosted_cpu_minutes: 20.0", text)
        self.assertIn("github_hosted_minutes:   3.0", text)

    def test_budget_within_policy_when_github_zero(self):
        report = estimate_ci_budget(
            [
                {"execution_target": "self_hosted", "estimated_cost": 8},
                {"execution_target": "local", "estimated_cost": 1},
            ]
        )
        self.assertEqual(report.github_hosted_minutes, 0.0)
        self.assertTrue(report.within_policy)


if __name__ == "__main__":
    unittest.main()
