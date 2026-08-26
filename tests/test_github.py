import unittest
from unittest.mock import patch

from nexus_harness.github import GitHub, GitHubError


def _ok(run, payload: str) -> None:
    run.return_value.stdout = payload
    run.return_value.stderr = ""
    run.return_value.returncode = 0


def _cmd(run) -> tuple[list, dict]:
    args, kwargs = run.call_args
    cmd = args[0]
    return list(cmd), kwargs


class GitHubTests(unittest.TestCase):
    @patch("nexus_harness.github.subprocess.run")
    def test_issue_create_uses_json_output(self, run):
        _ok(run, '{"number":123,"url":"https://github.com/x/y/issues/123"}')
        issue = GitHub().create_issue("x/y", "Bug: example", "body", ["type:bug"])
        self.assertEqual(issue.number, 123)
        self.assertEqual(issue.url, "https://github.com/x/y/issues/123")

        cmd, kwargs = _cmd(run)
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], "gh")
        self.assertFalse(kwargs.get("shell", False))
        self.assertIs(kwargs.get("shell"), False)
        self.assertIn("Bug: example", cmd)
        self.assertIn("body", cmd)
        self.assertIn("type:bug", cmd)

    @patch("nexus_harness.github.subprocess.run")
    def test_title_with_metacharacters_stays_one_argv(self, run):
        _ok(run, '{"number":1,"url":"https://github.com/x/y/issues/1"}')
        title = 'fix; rm -rf / && echo "$GH_TOKEN"'
        GitHub().create_issue("x/y", title, "details")
        cmd, kwargs = _cmd(run)
        self.assertIn(title, cmd)
        self.assertNotIsInstance(cmd, str)
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(cmd.count(title), 1)

    @patch("nexus_harness.github.subprocess.run")
    def test_nonzero_exit_includes_github_error_without_secrets(self, run):
        token = "ghp_supersecretTOKEN123"
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        run.return_value.stderr = (
            "GraphQL: Projects (classic) is being deprecated\n"
            f"GH_TOKEN={token}\n"
            f"GITHUB_TOKEN={token}\n"
            f"PAT={token}\n"
            f"Authorization: Bearer {token}\n"
            f"env dump: GH_TOKEN={token} PATH=/usr/bin\n"
        )
        with self.assertRaises(GitHubError) as raised:
            GitHub().create_issue("x/y", "Bug: example", "body")
        message = str(raised.exception)
        self.assertIn("GraphQL: Projects (classic) is being deprecated", message)
        self.assertNotIn(token, message)
        self.assertNotIn("ghp_", message)
        self.assertNotIn("Bearer ", message)
        self.assertNotIn(f"GH_TOKEN={token}", message)
        self.assertNotIn(f"GITHUB_TOKEN={token}", message)
        self.assertNotIn(f"PAT={token}", message)
        self.assertNotIn("Authorization: Bearer", message)
        self.assertNotIn("PATH=/usr/bin", message)
        self.assertNotIn("environ", message.lower())

    @patch("nexus_harness.github.subprocess.run")
    def test_edit_issue_sends_fields_as_argv(self, run):
        _ok(
            run,
            '{"number":9,"url":"https://github.com/x/y/issues/9","title":"Renamed"}',
        )
        issue = GitHub().edit_issue("x/y", 9, title="Renamed", body="updated")
        self.assertEqual(issue.number, 9)
        self.assertEqual(issue.title, "Renamed")
        cmd, kwargs = _cmd(run)
        self.assertIsInstance(cmd, list)
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("9", cmd)
        self.assertIn("Renamed", cmd)
        self.assertIn("updated", cmd)

    @patch("nexus_harness.github.subprocess.run")
    def test_find_issue_returns_first_json_match(self, run):
        _ok(
            run,
            '[{"number":44,"url":"https://github.com/x/y/issues/44","title":"Bug: example","state":"OPEN"}]',
        )
        issue = GitHub().find_issue("x/y", "Bug: example")
        self.assertIsNotNone(issue)
        self.assertEqual(issue.number, 44)
        cmd, kwargs = _cmd(run)
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("--search", cmd)
        self.assertIn("Bug: example", cmd)
        self.assertTrue(
            any(part == "--json" or part.startswith("--json") for part in cmd)
        )

    @patch("nexus_harness.github.subprocess.run")
    def test_find_issue_returns_none_when_empty(self, run):
        _ok(run, "[]")
        self.assertIsNone(GitHub().find_issue("x/y", "no-such-fingerprint"))

    @patch("nexus_harness.github.subprocess.run")
    def test_create_pr_parses_json(self, run):
        _ok(run, '{"number":7,"url":"https://github.com/x/y/pull/7"}')
        pr = GitHub().create_pr(
            "x/y", "Fix bug", "Closes #123", base="main", head="feat/x"
        )
        self.assertEqual(pr.number, 7)
        self.assertEqual(pr.url, "https://github.com/x/y/pull/7")
        cmd, kwargs = _cmd(run)
        self.assertIsInstance(cmd, list)
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("Fix bug", cmd)
        self.assertIn("Closes #123", cmd)
        self.assertIn("main", cmd)
        self.assertIn("feat/x", cmd)

    @patch("nexus_harness.github.subprocess.run")
    def test_view_pr_uses_json_fields(self, run):
        _ok(
            run,
            '{"number":7,"url":"https://github.com/x/y/pull/7","title":"Fix","state":"OPEN","isDraft":true}',
        )
        pr = GitHub().view_pr("x/y", 7)
        self.assertEqual(pr.number, 7)
        self.assertTrue(pr.is_draft)
        cmd, kwargs = _cmd(run)
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("7", cmd)
        self.assertTrue(
            any(part == "--json" or part.startswith("--json") for part in cmd)
        )

    @patch("nexus_harness.github.subprocess.run")
    def test_api_graphql_sends_query_as_argv_field(self, run):
        _ok(run, '{"data":{"viewer":{"login":"octocat"}}}')
        payload = GitHub().api_graphql(
            "query($login:String!){ user(login:$login){ id } }",
            {"login": "octocat"},
        )
        self.assertEqual(payload["data"]["viewer"]["login"], "octocat")
        cmd, kwargs = _cmd(run)
        self.assertIsInstance(cmd, list)
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("graphql", cmd)
        joined = " ".join(cmd)
        self.assertIn("query($login:String!)", joined)
        self.assertNotIn(";", cmd[0])

    @patch("nexus_harness.github.subprocess.run")
    def test_project_item_update_uses_argv_flags(self, run):
        _ok(run, '{"id":"PVTI_1"}')
        result = GitHub().project_item_update(
            item_id="PVTI_1",
            project_id="PVT_1",
            field_id="PVTF_status",
            text="In Progress",
        )
        self.assertEqual(result["id"], "PVTI_1")
        cmd, kwargs = _cmd(run)
        self.assertIsInstance(cmd, list)
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("PVTI_1", cmd)
        self.assertIn("PVT_1", cmd)
        self.assertIn("PVTF_status", cmd)
        self.assertIn("In Progress", cmd)
