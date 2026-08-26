import unittest
from pathlib import Path
from unittest.mock import Mock

from nexus_harness.config import load_toml
from nexus_harness.github import GitHub
from nexus_harness.project_sync import (
    lifecycle_to_project_status,
    load_project_fields,
    project_field_values,
    sync_project_item,
)
from nexus_harness.quality import QualityReport
from nexus_harness.security import SecurityReport


ROOT = Path(__file__).resolve().parents[1]
PROJECT_FIELDS = ROOT / "core" / "project" / "project-fields.toml"
_NODE_ID_MARKERS = ("PVT_", "PVTI_", "PVTF_", "PVTSSF_", "PVI_", "PN_")
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
    client.project_item_update.return_value = {"id": "item"}
    return client


def _sync(
    github, *, current, stage, gate_status, event=None, quality=None, security=None
):
    return sync_project_item(
        github,
        project_id="user-local-project",
        item_id="user-local-item",
        field_ids=FIELD_IDS,
        option_ids=OPTION_IDS,
        current_fields=current,
        stage=stage,
        gate_status=gate_status,
        event=event,
        quality_report=quality,
        security_report=security,
        authorize_remote_mutation=True,
    )


class ProjectSyncTests(unittest.TestCase):
    def test_stage_5_maps_to_in_progress(self):
        self.assertEqual(lifecycle_to_project_status(5, "PASS"), "In Progress")

    def test_blocked_maps_to_blocked(self):
        self.assertEqual(lifecycle_to_project_status(6, "BLOCKED"), "Blocked")

    def test_issue_created_maps_to_inbox(self):
        self.assertEqual(
            lifecycle_to_project_status(0, "PASS", event="issue_created"),
            "Inbox",
        )

    def test_acceptance_ready_maps_to_ready(self):
        self.assertEqual(
            lifecycle_to_project_status(1, "PASS", event="acceptance_ready"),
            "Ready",
        )
        self.assertEqual(lifecycle_to_project_status(1, "PASS"), "Ready")

    def test_pr_event_maps_to_review(self):
        self.assertEqual(
            lifecycle_to_project_status(5, "PASS", event="pr"),
            "Review",
        )

    def test_post_merge_maps_to_verifying(self):
        self.assertEqual(
            lifecycle_to_project_status(9, "PASS", event="post_merge"),
            "Verifying",
        )

    def test_verified_completion_maps_to_done(self):
        self.assertEqual(
            lifecycle_to_project_status(9, "PASS", event="verified_completion"),
            "Done",
        )

    def test_gate_failure_maps_to_blocked(self):
        self.assertEqual(lifecycle_to_project_status(5, "FAIL"), "Blocked")
        self.assertEqual(
            lifecycle_to_project_status(5, "PASS", event="gate_failure"),
            "Blocked",
        )

    def test_user_event_overrides_stage_table(self):
        self.assertEqual(lifecycle_to_project_status(6, "PASS"), "Verifying")
        self.assertEqual(
            lifecycle_to_project_status(6, "PASS", event="pr"),
            "Review",
        )

    def test_quality_security_come_from_reports(self):
        fields = project_field_values(
            stage=5,
            gate_status="PASS",
            quality_report=QualityReport(gate="PASS"),
            security_report=SecurityReport(gate="FAIL"),
        )
        self.assertEqual(fields["Quality"], "PASS")
        self.assertEqual(fields["Security"], "FAIL")
        self.assertEqual(fields["Status"], "Blocked")

    def test_sync_sends_only_changed_fields(self):
        github = _github()
        result = _sync(
            github,
            current={"Status": "Inbox", "Quality": "PASS", "Security": "PASS"},
            stage=5,
            gate_status="PASS",
            quality={"gate": "PASS"},
            security={"gate": "PASS"},
        )
        self.assertEqual(result.status, "In Progress")
        self.assertEqual(result.updated, ("Status",))
        self.assertEqual(github.project_item_update.call_count, 1)
        args, kwargs = github.project_item_update.call_args
        self.assertEqual(args[0], "user-local-item")
        self.assertEqual(args[1], "user-local-project")
        self.assertEqual(args[2], "user-field-status")
        self.assertEqual(kwargs.get("single_select_option_id"), "opt-progress")
        self.assertIsNone(kwargs.get("text"))

    def test_sync_skips_when_unchanged(self):
        github = _github()
        result = _sync(
            github,
            current={
                "Status": "In Progress",
                "Quality": "PASS",
                "Security": "PASS",
            },
            stage=5,
            gate_status="PASS",
            quality={"gate": "PASS"},
            security={"gate": "PASS"},
        )
        self.assertEqual(result.updated, ())
        github.project_item_update.assert_not_called()

    def test_quality_fail_updates_status_and_quality(self):
        github = _github()
        result = _sync(
            github,
            current={"Status": "In Progress", "Quality": "PASS", "Security": "PASS"},
            stage=5,
            gate_status="PASS",
            quality={"gate": "FAIL"},
            security={"gate": "PASS"},
        )
        self.assertEqual(result.status, "Blocked")
        self.assertEqual(set(result.updated), {"Status", "Quality"})
        self.assertEqual(github.project_item_update.call_count, 2)
        sent = {
            call.args[2]: call.kwargs.get("single_select_option_id")
            for call in github.project_item_update.call_args_list
        }
        self.assertEqual(sent["user-field-status"], "opt-blocked")
        self.assertEqual(sent["user-field-quality"], "opt-quality-fail")
        self.assertNotIn("user-field-security", sent)

    def test_unauthorized_does_not_call_update(self):
        github = _github()
        result = sync_project_item(
            github,
            project_id="user-local-project",
            item_id="user-local-item",
            field_ids={"Status": "user-field-status"},
            current_fields={"Status": "Inbox"},
            stage=5,
            gate_status="PASS",
        )
        self.assertEqual(result.status, "In Progress")
        self.assertEqual(result.changed, ("Status",))
        self.assertEqual(result.updated, ())
        github.project_item_update.assert_not_called()

    def test_core_toml_preserves_fields_and_has_no_node_ids(self):
        raw = PROJECT_FIELDS.read_text(encoding="utf-8")
        payload = load_toml(PROJECT_FIELDS)
        loaded = load_project_fields()

        self.assertEqual(payload["project"]["name"], "Nexus Engineering")
        self.assertTrue(payload["project"]["id_stored_in_user_configuration"])
        self.assertEqual(
            list(payload["fields"]["names"]),
            [
                "Project",
                "Type",
                "Status",
                "Priority",
                "Area",
                "Client",
                "Iteration",
                "Risk",
                "Environment",
                "Quality",
                "Security",
                "Target date",
            ],
        )
        self.assertEqual(
            list(payload["status"]["values"]),
            [
                "Inbox",
                "Planned",
                "Ready",
                "In Progress",
                "Review",
                "Blocked",
                "Verifying",
                "Done",
            ],
        )
        self.assertEqual(payload["status_from_lifecycle"]["5"], "In Progress")
        self.assertEqual(payload["status_from_lifecycle"]["blocked"], "Blocked")
        events = payload["status_from_event"]
        self.assertEqual(events["issue_created"], "Inbox")
        self.assertEqual(events["acceptance_ready"], "Ready")
        self.assertEqual(events["implement"], "In Progress")
        self.assertEqual(events["pr"], "Review")
        self.assertEqual(events["gate_failure"], "Blocked")
        self.assertEqual(events["post_merge"], "Verifying")
        self.assertEqual(events["verified_completion"], "Done")
        self.assertEqual(payload["owner"]["github_login"], "Rubens-Marques")
        self.assertNotIn("id", payload["project"])
        self.assertNotIn("node_id", payload.get("project", {}))
        self.assertNotIn("project_id", payload)
        self.assertEqual(loaded["status_from_event"]["pr"], "Review")
        for marker in _NODE_ID_MARKERS:
            self.assertNotIn(marker, raw)

    def test_core_toml_does_not_store_opaque_project_ids(self):
        payload = load_toml(PROJECT_FIELDS)
        blob = repr(payload)
        self.assertNotIn("PVT_", blob)
        self.assertNotIn("PVTI_", blob)
        self.assertNotIn("PVTF_", blob)


if __name__ == "__main__":
    unittest.main()
