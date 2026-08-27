"""Actionable-incident policy — network-free unit tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nexus_harness.incident_policy import (
    ACTION_CREATE,
    ACTION_IGNORE,
    ACTION_POLICY_FAILURE,
    ACTION_UPDATE,
    classify_incident,
    incident_marker,
    load_incident_policy,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_TOML = ROOT / "core" / "observability" / "incidents.toml"


class IncidentPolicyTests(unittest.TestCase):
    def test_single_low_impact_occurrence_is_not_issue(self):
        result = classify_incident(
            occurrences=1, affected_users=1, regression=False, fatal=False
        )
        self.assertEqual(result.action, ACTION_IGNORE)

    def test_release_regression_creates_issue(self):
        result = classify_incident(
            occurrences=4, affected_users=3, regression=True, fatal=False
        )
        self.assertEqual(result.action, ACTION_CREATE)

    def test_fatal_creates_issue(self):
        result = classify_incident(
            occurrences=1, affected_users=1, regression=False, fatal=True
        )
        self.assertEqual(result.action, ACTION_CREATE)

    def test_occurrence_threshold_boundary(self):
        policy = load_incident_policy(POLICY_TOML)
        below = policy.min_occurrences_create - 1
        at = policy.min_occurrences_create
        self.assertGreaterEqual(at, 2)
        self.assertEqual(
            classify_incident(
                occurrences=below, affected_users=1, regression=False, fatal=False
            ).action,
            ACTION_IGNORE,
        )
        self.assertEqual(
            classify_incident(
                occurrences=at, affected_users=1, regression=False, fatal=False
            ).action,
            ACTION_CREATE,
        )

    def test_affected_user_threshold_creates(self):
        policy = load_incident_policy(POLICY_TOML)
        self.assertEqual(
            classify_incident(
                occurrences=1,
                affected_users=policy.min_affected_users_create,
                regression=False,
                fatal=False,
            ).action,
            ACTION_CREATE,
        )

    def test_security_adjacent_creates(self):
        result = classify_incident(
            occurrences=1,
            affected_users=1,
            regression=False,
            fatal=False,
            security_adjacent=True,
        )
        self.assertEqual(result.action, ACTION_CREATE)

    def test_matching_open_issue_updates_instead_of_create(self):
        fingerprint = "abc" * 16 + "abcd"
        marker = incident_marker(fingerprint)
        open_issues = [
            {
                "number": 42,
                "title": "unrelated title",
                "body": f"hello\n{marker}\n",
                "state": "open",
            }
        ]
        result = classify_incident(
            occurrences=9,
            affected_users=9,
            regression=True,
            fatal=True,
            fingerprint=fingerprint,
            open_issues=open_issues,
        )
        self.assertEqual(result.action, ACTION_UPDATE)
        self.assertEqual(result.issue_number, 42)

    def test_title_fuzzy_match_does_not_count_as_dedup(self):
        fingerprint = "fff" * 16 + "ffff"
        open_issues = [
            {
                "number": 7,
                "title": f"TypeError fetchLead {fingerprint}",
                "body": "no marker here",
                "state": "open",
            }
        ]
        result = classify_incident(
            occurrences=9,
            affected_users=9,
            regression=True,
            fingerprint=fingerprint,
            open_issues=open_issues,
        )
        self.assertEqual(result.action, ACTION_CREATE)
        self.assertIsNone(result.issue_number)

    def test_invalid_policy_fails_closed_for_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incidents.toml"
            path.write_text("thresholds = true\n", encoding="utf-8")
            result = classify_incident(
                occurrences=99,
                affected_users=99,
                regression=True,
                fatal=True,
                policy_path=path,
            )
            self.assertEqual(result.action, ACTION_POLICY_FAILURE)
            self.assertNotEqual(result.action, ACTION_CREATE)

    def test_core_policy_is_conservative(self):
        policy = load_incident_policy(POLICY_TOML)
        self.assertGreaterEqual(policy.min_occurrences_create, 3)
        self.assertGreaterEqual(policy.min_affected_users_create, 2)


if __name__ == "__main__":
    unittest.main()
