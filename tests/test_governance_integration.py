"""Mocked end-to-end GitHub governance proof for a bounded SDR bug.

Glues existing modules. GitHub is mocked — no real mutations.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from nexus_harness.completion import promote_acceptance
from nexus_harness.evidence import Evidence
from nexus_harness.github import GitHub, Issue
from nexus_harness.hierarchy import apply_hierarchy, tracking_shape
from nexus_harness.project import ProjectRegistry
from nexus_harness.project_sync import lifecycle_to_project_status, sync_project_item
from nexus_harness.pull_request import ready_to_merge, render_pr_body
from nexus_harness.quality import QualityReport
from nexus_harness.security import SecurityReport
from nexus_harness.state import AcceptanceCriterion, TaskState
from nexus_harness.tracking import ensure_issue


REPO = "Rubens-Marques/SDR-Plataform"
ISSUE = 123
DIFF = "abc"
FIELD_IDS = {
    "Status": "user-field-status",
    "Quality": "user-field-quality",
    "Security": "user-field-security",
}
OPTION_IDS = {
    "Status": {
        "Inbox": "opt-inbox",
        "Ready": "opt-ready",
        "In Progress": "opt-progress",
        "Review": "opt-review",
        "Blocked": "opt-blocked",
        "Verifying": "opt-verifying",
        "Done": "opt-done",
    },
    "Quality": {"PASS": "opt-quality-pass", "FAIL": "opt-quality-fail"},
    "Security": {"PASS": "opt-security-pass", "FAIL": "opt-security-fail"},
}


def _github() -> Mock:
    client = Mock(spec=GitHub)
    client.find_issue.return_value = None
    client.create_issue.return_value = Issue(
        number=ISSUE,
        url=f"https://github.com/{REPO}/issues/{ISSUE}",
        title="Fix login 500",
        state="OPEN",
    )
    client.project_item_update.return_value = {"id": "item"}
    return client


def _sync(github, board, *, stage, event=None):
    quality = QualityReport(gate="PASS", diff_hash=DIFF)
    security = SecurityReport(gate="PASS", diff_hash=DIFF)
    result = sync_project_item(
        github,
        project_id="user-local-project",
        item_id="user-local-item",
        field_ids=FIELD_IDS,
        option_ids=OPTION_IDS,
        current_fields=board,
        stage=stage,
        gate_status="PASS",
        event=event,
        quality_report=quality,
        security_report=security,
        authorize_remote_mutation=True,
    )
    board["Status"] = result.status
    board["Quality"] = "PASS"
    board["Security"] = "PASS"
    return result


def _status_texts(github) -> list[str]:
    texts = []
    for call in github.project_item_update.call_args_list:
        field_id = call.args[2]
        if field_id == FIELD_IDS["Status"]:
            texts.append(call.kwargs.get("single_select_option_id"))
    return texts


def _green_state(state: TaskState) -> None:
    state.tracking_required = True
    state.current_diff_hash = DIFF
    state.acceptance = [
        AcceptanceCriterion(id="AC-1", statement="login no longer returns 500"),
    ]
    evidence = Evidence("ev-1", "pytest", 0, DIFF, "base-1", "repro gone")
    state.evidence = [evidence]
    promote_acceptance(state, evidence)
    state.quality_gate = QualityReport(gate="PASS", diff_hash=DIFF)
    state.security_gate = SecurityReport(gate="PASS", diff_hash=DIFF)
    state.review_gate = "PASS"
    state.verified_diff_hash = DIFF
    state.reviewed_diff_hash = DIFF
    state.findings = []


@patch("subprocess.run", side_effect=AssertionError("real subprocess forbidden"))
@patch(
    "nexus_harness.github.subprocess.run",
    side_effect=AssertionError("real gh forbidden"),
)
class GovernanceIntegrationTests(unittest.TestCase):
    def test_bounded_bug_governance_flow(self, *_):
        project = ProjectRegistry.load().by_repository(REPO)
        self.assertEqual(project.id, "sdr-platform")
        self.assertEqual(project.repository, REPO)

        shape = tracking_shape("bounded", "bug")
        self.assertEqual(shape, ("bug",))
        self.assertNotIn("epic", shape)
        self.assertNotIn("task", shape)

        github = _github()
        state = TaskState.new("sdr-login-500", project.repository)
        tracking = ensure_issue(
            state,
            github,
            title="Fix login 500",
            work_type="bug",
            repo=project.repository,
            authorize_remote_mutation=True,
        )
        self.assertEqual(tracking.issue, ISSUE)
        self.assertEqual(state.issue, ISSUE)
        self.assertTrue(tracking.created)
        self.assertEqual(github.create_issue.call_count, 1)
        self.assertEqual(github.create_issue.call_args.args[0], REPO)

        hierarchy = apply_hierarchy(
            github,
            repo=project.repository,
            scope="bounded",
            work_type="bug",
            parent=state.issue,
            children=(999,),
            authorize_remote_mutation=True,
            state=state,
        )
        self.assertEqual(hierarchy.shape, ("bug",))
        self.assertEqual(hierarchy.children, ())
        self.assertFalse(hierarchy.linked)
        self.assertEqual(getattr(state, "child_issues", ()), ())
        github.api_graphql.assert_not_called()
        github.create_issue.assert_called_once()
        github.create_pr.assert_not_called()

        board: dict[str, str] = {}
        self.assertEqual(lifecycle_to_project_status(1, "PASS"), "Ready")
        self.assertEqual(
            _sync(github, board, stage=1, event="acceptance_ready").status, "Ready"
        )
        self.assertEqual(
            lifecycle_to_project_status(5, "PASS", event="implement"),
            "In Progress",
        )
        self.assertEqual(
            _sync(github, board, stage=5, event="implement").status, "In Progress"
        )

        body = render_pr_body(
            issue=state.issue,
            partial=False,
            summary="Fix login 500 on SDR Platform",
        )
        self.assertIn("Closes #123", body)
        self.assertNotIn("Refs #123", body)

        self.assertEqual(lifecycle_to_project_status(5, "PASS", event="pr"), "Review")
        self.assertEqual(_sync(github, board, stage=5, event="pr").status, "Review")

        _green_state(state)
        merge = ready_to_merge(state)
        self.assertEqual(merge.status, "READY_TO_MERGE")
        self.assertEqual(merge.reasons, [])

        self.assertEqual(
            lifecycle_to_project_status(9, "PASS", event="post_merge"),
            "Verifying",
        )
        self.assertEqual(
            _sync(github, board, stage=9, event="post_merge").status, "Verifying"
        )
        self.assertEqual(
            lifecycle_to_project_status(9, "PASS", event="verified_completion"),
            "Done",
        )
        self.assertEqual(
            _sync(github, board, stage=9, event="verified_completion").status,
            "Done",
        )

        self.assertEqual(
            _status_texts(github),
            ["opt-ready", "opt-progress", "opt-review", "opt-verifying", "opt-done"],
        )
        self.assertEqual(github.create_issue.call_count, 1)
        github.create_pr.assert_not_called()
        github.api_graphql.assert_not_called()


if __name__ == "__main__":
    unittest.main()
