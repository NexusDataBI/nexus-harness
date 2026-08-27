"""Hermetic PostHog incident lifecycle — network-free."""

from __future__ import annotations

import unittest

from nexus_harness.github import Issue
from nexus_harness.incident_issue import apply_incident_issue
from nexus_harness.incident_policy import (
    ACTION_CREATE,
    ACTION_IGNORE,
    ACTION_UPDATE,
    classify_incident,
    incident_marker,
)
from nexus_harness.incidents import normalize_posthog_problem
from nexus_harness.postdeploy import (
    GATE_INSUFFICIENT,
    GATE_PASS,
    evaluate_postdeploy,
)

DIGEST_A = "sha256:" + ("a" * 64)


def _occurrence(n: int, *, release: str = "aaa111", env: str = "production") -> dict:
    return {
        "project": "sdr-platform",
        "environment": env,
        "error_type": "TypeError",
        "stack_location": "src/modules/leads/service.ts:fetchLead",
        "route": "/api/leads",
        "release": release,
        "occurrences": n,
        "affected_users": max(1, n - 1),
        "first_seen": "2026-08-25T10:00:00Z",
        "last_seen": f"2026-08-25T1{n}:00:00Z",
        "problem_id": "err_ph_1001",
        "session_id": f"sess_{n}",
        "request_id": f"req_{n}",
    }


class FakeGitHub:
    def __init__(self):
        self.created: list[dict] = []
        self.edited: list[dict] = []
        self._next = 501

    def create_issue(self, repo, title, body, labels=None):
        number = self._next
        self._next += 1
        self.created.append(
            {
                "repo": repo,
                "title": title,
                "body": body,
                "labels": labels,
                "number": number,
            }
        )
        return Issue(number=number, url=f"https://github.com/x/y/issues/{number}")

    def edit_issue(self, repo, number, **fields):
        self.edited.append({"repo": repo, "number": number, **fields})
        return Issue(number=number, url=f"https://github.com/x/y/issues/{number}")


class IncidentIntegrationTests(unittest.TestCase):
    def test_three_occurrences_create_once_then_update_then_fixed_release(self):
        github = FakeGitHub()
        open_issues: list[dict] = []
        creates = 0
        updates = 0
        issue_number = None
        fingerprint = None

        for n in (1, 2, 3, 4, 5):
            candidate = normalize_posthog_problem(_occurrence(n))
            if fingerprint is None:
                fingerprint = candidate.fingerprint
            else:
                self.assertEqual(candidate.fingerprint, fingerprint)
            decision = classify_incident(
                occurrences=candidate.occurrences,
                affected_users=candidate.affected_users,
                regression=True,
                fatal=False,
                fingerprint=candidate.fingerprint,
                open_issues=open_issues,
            )
            if n < 3:
                self.assertEqual(decision.action, ACTION_IGNORE)
                continue
            result = apply_incident_issue(
                candidate,
                github,
                repo="x/y",
                action=decision.action,
                digest=DIGEST_A,
                issue_number=decision.issue_number,
                authorize_remote_mutation=False,
            )
            if n == 3:
                self.assertEqual(decision.action, ACTION_CREATE)
                self.assertEqual(result.action, ACTION_CREATE)
                creates += 1
                issue_number = 501
                open_issues.append(
                    {
                        "number": issue_number,
                        "title": result.request_title,
                        "body": result.request_body,
                        "state": "open",
                    }
                )
                self.assertIn(incident_marker(fingerprint), result.request_body)
            else:
                self.assertEqual(decision.action, ACTION_UPDATE)
                self.assertEqual(result.action, ACTION_UPDATE)
                self.assertEqual(result.issue_number, issue_number)
                updates += 1
                open_issues[0]["body"] = result.request_body

        self.assertEqual(creates, 1)
        self.assertEqual(updates, 2)
        self.assertEqual(len(github.created), 0)  # mutation still off

        fixed = evaluate_postdeploy(
            health=True,
            smoke=True,
            new_error_regression=False,
            observations_available=20,
            minimum_sample=5,
        )
        self.assertEqual(fixed.gate, GATE_PASS)
        self.assertTrue(fixed.issue_close_eligible)

    def test_insufficient_telemetry_does_not_close_issue(self):
        result = evaluate_postdeploy(
            health=True,
            smoke=True,
            new_error_regression=False,
            observations_available=0,
            minimum_sample=5,
        )
        self.assertEqual(result.gate, GATE_INSUFFICIENT)
        self.assertFalse(result.issue_close_eligible)


if __name__ == "__main__":
    unittest.main()
