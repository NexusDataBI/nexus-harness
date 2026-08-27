"""Runtime incident → GitHub Issue renderer — network-free tests."""

from __future__ import annotations

import unittest

from nexus_harness.github import Issue
from nexus_harness.incident_issue import (
    ISSUE_SOURCE,
    ISSUE_WORK_TYPE,
    apply_incident_issue,
    render_incident_issue,
)
from nexus_harness.incident_policy import ACTION_CREATE, ACTION_UPDATE, incident_marker
from nexus_harness.incidents import IncidentCandidate
from nexus_harness.tracking import BUG_RCA_SECTIONS, CONTRACT_SECTIONS


SECRET = "phx_supersecret_PERSONAL_KEY_do_not_leak"
COOKIE = "session=abc; auth=xyz"
DIGEST = "sha256:" + ("a" * 64)


def _candidate(**overrides) -> IncidentCandidate:
    payload = dict(
        project="sdr-platform",
        environment="production",
        error_type="TypeError",
        stack_location="src/modules/leads/service.ts:fetchLead",
        route="/api/leads",
        release="abc123def",
        occurrences=4,
        affected_users=3,
        first_seen="2026-08-25T10:00:00Z",
        last_seen="2026-08-25T12:15:00Z",
        fingerprint="ab" * 32,
        proximate_symptom="KNOWN",
        root_cause="UNKNOWN",
        escape_cause="UNKNOWN",
        symptom="Cannot read properties of undefined",
        provider_problem_id="err_ph_1001",
        session_ids=("sess_aaa111",),
        session_links=("https://us.posthog.com/project/1/replay/sess_aaa111",),
    )
    payload.update(overrides)
    return IncidentCandidate(**payload)


class FakeGitHub:
    def __init__(self):
        self.created: list[dict] = []
        self.edited: list[dict] = []
        self.create_result = Issue(number=88, url="https://github.com/x/y/issues/88")

    def create_issue(self, repo, title, body, labels=None):
        self.created.append(
            {"repo": repo, "title": title, "body": body, "labels": labels}
        )
        return self.create_result

    def edit_issue(self, repo, number, **fields):
        self.edited.append({"repo": repo, "number": number, **fields})
        return Issue(number=number, url=f"https://github.com/x/y/issues/{number}")


class IncidentIssueTests(unittest.TestCase):
    def test_body_includes_contract_release_and_marker(self):
        body = render_incident_issue(_candidate(), digest=DIGEST)
        for heading in CONTRACT_SECTIONS + BUG_RCA_SECTIONS:
            self.assertIn(f"## {heading}", body)
        self.assertIn("sdr-platform", body)
        self.assertIn("production", body)
        self.assertIn("abc123def", body)
        self.assertIn(DIGEST, body)
        self.assertIn("4", body)
        self.assertIn("3", body)
        self.assertIn("err_ph_1001", body)
        self.assertIn("sess_aaa111", body)
        self.assertIn(incident_marker("ab" * 32), body)
        self.assertIn(ISSUE_WORK_TYPE, body)
        self.assertIn(ISSUE_SOURCE, body)
        self.assertRegex(body, r"(?im)^## Root Cause\s*$[\s\S]*?UNKNOWN")
        self.assertRegex(body, r"(?im)^## Escape Cause\s*$[\s\S]*?UNKNOWN")
        self.assertRegex(body, r"(?im)^## Reproduction\s*$")
        self.assertRegex(body, r"(?im)^## Acceptance Criteria\s*$")

    def test_body_never_includes_secrets_or_raw_session_contents(self):
        body = render_incident_issue(
            _candidate(),
            digest=DIGEST,
            personal_api_key=SECRET,
            cookies=COOKIE,
            authorization="Bearer supersecret",
        )
        self.assertNotIn(SECRET, body)
        self.assertNotIn(COOKIE, body)
        self.assertNotIn("Bearer supersecret", body)
        self.assertNotIn("Authorization", body)
        self.assertNotRegex(body, r"(?i)phx_")

    def test_body_redacts_exception_secrets_and_strips_replay_query(self):
        candidate = _candidate(
            symptom="boom cookie=session=raw token=secret alice@example.com",
            session_links=(
                "https://us.posthog.com/project/1/replay/sess_aaa111?personal_api_key=nope",
            ),
        )
        # Candidate links may still be raw; renderer/normalizer must not publish query.
        body = render_incident_issue(candidate, digest=DIGEST)
        self.assertNotIn("alice@example.com", body)
        self.assertNotIn("token=secret", body)
        self.assertNotIn("session=raw", body)
        self.assertNotIn("personal_api_key=nope", body)
        self.assertEqual(ISSUE_WORK_TYPE, "bug")
        self.assertEqual(ISSUE_SOURCE, "runtime_incident/posthog")

    def test_remote_mutation_default_is_false(self):
        github = FakeGitHub()
        result = apply_incident_issue(
            _candidate(),
            github,
            repo="x/y",
            action=ACTION_CREATE,
            digest=DIGEST,
        )
        self.assertFalse(result.mutated)
        self.assertEqual(result.action, ACTION_CREATE)
        self.assertEqual(github.created, [])
        self.assertTrue(result.request_body)
        self.assertIn(incident_marker("ab" * 32), result.request_body)

    def test_authorized_create_uses_existing_github_client(self):
        github = FakeGitHub()
        result = apply_incident_issue(
            _candidate(),
            github,
            repo="x/y",
            action=ACTION_CREATE,
            digest=DIGEST,
            authorize_remote_mutation=True,
        )
        self.assertTrue(result.mutated)
        self.assertEqual(len(github.created), 1)
        self.assertEqual(github.created[0]["repo"], "x/y")
        self.assertIn(incident_marker("ab" * 32), github.created[0]["body"])
        self.assertEqual(result.issue_number, 88)

    def test_update_existing_does_not_create_second_issue(self):
        github = FakeGitHub()
        result = apply_incident_issue(
            _candidate(occurrences=5),
            github,
            repo="x/y",
            action=ACTION_UPDATE,
            issue_number=42,
            digest=DIGEST,
            authorize_remote_mutation=True,
        )
        self.assertEqual(result.action, ACTION_UPDATE)
        self.assertEqual(github.created, [])
        self.assertEqual(result.issue_number, 42)
        self.assertEqual(github.edited[0]["number"], 42)


if __name__ == "__main__":
    unittest.main()
