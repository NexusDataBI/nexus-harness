import unittest

from nexus_harness.github import Issue
from nexus_harness.state import TaskState
from nexus_harness.tracking import (
    BUG_RCA_SECTIONS,
    CONTRACT_SECTIONS,
    ensure_issue,
    issue_body,
    tracking_required,
)


class FakeGitHub:
    def __init__(self):
        self.viewed: list[tuple[str, int]] = []
        self.searched: list[tuple[str, str]] = []
        self.created: list[dict] = []
        self.view_result: Issue | None = None
        self.search_result: Issue | None = None
        self.create_result = Issue(
            number=99,
            url="https://github.com/x/y/issues/99",
            title="created",
            state="OPEN",
        )

    def view_issue(self, repo: str, number: int) -> Issue | None:
        self.viewed.append((repo, number))
        return self.view_result

    def find_issue(self, repo: str, query: str) -> Issue | None:
        self.searched.append((repo, query))
        return self.search_result

    def create_issue(self, repo: str, title: str, body: str, labels=None) -> Issue:
        self.created.append(
            {"repo": repo, "title": title, "body": body, "labels": labels}
        )
        return self.create_result


def _state(*, issue: int | None = None) -> TaskState:
    state = TaskState.new("task-1", "x/y")
    state.issue = issue
    return state


class TrackingTests(unittest.TestCase):
    def test_change_requires_issue(self):
        self.assertTrue(tracking_required("change", mutable=True))

    def test_read_only_inspect_does_not_require_issue(self):
        self.assertFalse(tracking_required("inspect", mutable=False))

    def test_mutable_work_types_require_issue(self):
        for work_type in ("bugfix", "improvement", "feature", "migration"):
            with self.subTest(work_type=work_type):
                self.assertTrue(tracking_required(work_type, mutable=True))

    def test_research_is_not_required_by_default(self):
        self.assertFalse(tracking_required("research"))

    def test_existing_open_issue_is_reused(self):
        github = FakeGitHub()
        github.view_result = Issue(
            number=12,
            url="https://github.com/x/y/issues/12",
            title="Fix login",
            state="OPEN",
        )
        state = _state(issue=12)

        result = ensure_issue(
            state,
            github,
            title="Fix login",
            work_type="change",
        )

        self.assertEqual(state.issue, 12)
        self.assertEqual(result.issue, 12)
        self.assertEqual(result.url, "https://github.com/x/y/issues/12")
        self.assertEqual(github.viewed, [("x/y", 12)])
        self.assertEqual(github.created, [])

    def test_closed_existing_issue_falls_through_to_search(self):
        github = FakeGitHub()
        github.view_result = Issue(
            number=12,
            url="https://github.com/x/y/issues/12",
            title="Fix login",
            state="CLOSED",
        )
        github.search_result = Issue(
            number=44,
            url="https://github.com/x/y/issues/44",
            title="Fix login",
            state="OPEN",
        )
        state = _state(issue=12)

        result = ensure_issue(
            state,
            github,
            title="Fix login",
            work_type="change",
            fingerprint="login-500",
        )

        self.assertEqual(state.issue, 44)
        self.assertEqual(result.issue, 44)
        self.assertEqual(github.viewed, [("x/y", 12)])
        self.assertEqual(github.searched, [("x/y", "login-500")])
        self.assertEqual(github.created, [])

    def test_search_hit_links_and_does_not_create(self):
        github = FakeGitHub()
        github.search_result = Issue(
            number=44,
            url="https://github.com/x/y/issues/44",
            title="Fix login",
            state="OPEN",
        )
        state = _state()

        result = ensure_issue(
            state,
            github,
            title="Fix login",
            work_type="feature",
            fingerprint="login-500",
            authorize_remote_mutation=True,
        )

        self.assertEqual(state.issue, 44)
        self.assertEqual(result.issue, 44)
        self.assertEqual(github.searched, [("x/y", "login-500")])
        self.assertEqual(github.created, [])

    def test_no_match_unauthorized_does_not_create(self):
        github = FakeGitHub()
        state = _state()

        result = ensure_issue(
            state,
            github,
            title="Add export",
            work_type="feature",
        )

        self.assertIsNone(state.issue)
        self.assertIsNone(result.issue)
        self.assertFalse(result.created)
        self.assertEqual(github.created, [])

    def test_no_match_authorized_creates_once(self):
        github = FakeGitHub()
        state = _state()

        result = ensure_issue(
            state,
            github,
            title="Add export",
            work_type="feature",
            authorize_remote_mutation=True,
        )

        self.assertEqual(state.issue, 99)
        self.assertEqual(result.issue, 99)
        self.assertTrue(result.created)
        self.assertEqual(len(github.created), 1)
        self.assertEqual(github.created[0]["title"], "Add export")
        self.assertEqual(github.created[0]["repo"], "x/y")
        created_body = github.created[0]["body"]
        self.assertIn("Summary", created_body)
        self.assertNotIn("Root Cause", created_body)
        self.assertEqual(github.searched, [])

    def test_title_is_not_used_as_search_without_fingerprint(self):
        github = FakeGitHub()
        github.search_result = Issue(
            number=7,
            url="https://github.com/x/y/issues/7",
            title="unrelated",
            state="OPEN",
        )
        state = _state()
        result = ensure_issue(
            state,
            github,
            title="Add export",
            work_type="feature",
            authorize_remote_mutation=True,
        )
        self.assertEqual(github.searched, [])
        self.assertEqual(result.issue, 99)
        self.assertTrue(result.created)

    def test_bug_body_includes_rca_sections(self):
        body = issue_body("bugfix", {"Summary": "Login 500"})
        for heading in CONTRACT_SECTIONS:
            self.assertIn(heading, body)
        for heading in BUG_RCA_SECTIONS:
            self.assertIn(heading, body)

    def test_feature_body_omits_empty_rca_ceremony(self):
        body = issue_body("feature", {"Summary": "Add export"})
        for heading in CONTRACT_SECTIONS:
            self.assertIn(heading, body)
        for heading in BUG_RCA_SECTIONS:
            self.assertNotIn(heading, body)
