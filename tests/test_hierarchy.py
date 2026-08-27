import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from nexus_harness.github import GitHub
from nexus_harness.hierarchy import apply_hierarchy, recover_hierarchy, tracking_shape
from nexus_harness.state import TaskState, load_task_state, save_task_state


class HierarchyTests(unittest.TestCase):
    def test_bounded_bug_is_single_issue(self):
        shape = tracking_shape(scope="bounded", work_type="bug")
        self.assertEqual(shape, ("bug",))

    def test_architectural_feature_can_have_epic_and_tasks(self):
        shape = tracking_shape(scope="architectural", work_type="feature")
        self.assertEqual(shape, ("epic", "feature", "task"))

    def test_bounded_improvement_is_single_issue(self):
        shape = tracking_shape(scope="bounded", work_type="improvement")
        self.assertEqual(shape, ("improvement",))

    def test_ordinary_feature_has_no_empty_children(self):
        shape = tracking_shape(scope="ordinary", work_type="feature")
        self.assertEqual(shape, ("feature",))
        self.assertNotIn("task", shape)

    def test_ordinary_feature_adds_tasks_only_for_independent_deliverables(self):
        shape = tracking_shape(
            scope="ordinary",
            work_type="feature",
            independent_deliverables=("export csv", "export xlsx"),
        )
        self.assertEqual(shape, ("feature", "task"))

    def test_long_horizon_feature_uses_epic_shape(self):
        self.assertEqual(
            tracking_shape(scope="long-horizon", work_type="feature"),
            ("epic", "feature", "task"),
        )

    def test_blank_deliverables_do_not_invent_task_shape(self):
        shape = tracking_shape(
            scope="ordinary",
            work_type="feature",
            independent_deliverables=("  ", ""),
        )
        self.assertEqual(shape, ("feature",))

    def test_apply_hierarchy_unauthorized_does_not_call_graphql(self):
        github = Mock(spec=GitHub)
        result = apply_hierarchy(
            github,
            repo="x/y",
            scope="architectural",
            work_type="feature",
            parent=10,
            children=(11, 12),
        )
        self.assertEqual(result.shape, ("epic", "feature", "task"))
        self.assertEqual(result.parent, 10)
        self.assertEqual(result.children, (11, 12))
        self.assertFalse(result.linked)
        github.api_graphql.assert_not_called()
        github.create_issue.assert_not_called()

    def test_apply_hierarchy_authorized_links_via_graphql(self):
        github = Mock(spec=GitHub)
        github.api_graphql.return_value = {"data": {"addSubIssue": {}}}

        result = apply_hierarchy(
            github,
            repo="x/y",
            scope="architectural",
            work_type="feature",
            parent=10,
            children=(11, 12),
            parent_id="I_parent",
            child_ids=("I_child_11", "I_child_12"),
            authorize_remote_mutation=True,
        )

        self.assertTrue(result.linked)
        self.assertEqual(result.parent, 10)
        self.assertEqual(result.children, (11, 12))
        self.assertEqual(github.api_graphql.call_count, 2)
        github.create_issue.assert_not_called()
        linked = []
        for call in github.api_graphql.call_args_list:
            query = call.args[0]
            variables = (
                call.args[1] if len(call.args) > 1 else call.kwargs.get("variables")
            )
            self.assertIn("addSubIssue", query)
            self.assertIn("$parent: ID!", query)
            self.assertNotIn("Int!", query)
            self.assertNotIn("$repo", query)
            self.assertEqual(variables["parent"], "I_parent")
            self.assertNotIn("repo", variables)
            linked.append(variables["child"])
        self.assertEqual(linked, ["I_child_11", "I_child_12"])

    def test_numeric_issue_numbers_are_not_sent_as_graphql_ids(self):
        github = Mock(spec=GitHub)
        result = apply_hierarchy(
            github,
            repo="x/y",
            scope="architectural",
            work_type="feature",
            parent=10,
            children=(11, 12),
            authorize_remote_mutation=True,
        )
        self.assertFalse(result.linked)
        self.assertEqual(result.parent, 10)
        self.assertEqual(result.children, (11, 12))
        github.api_graphql.assert_not_called()

    def test_apply_hierarchy_does_not_create_empty_children(self):
        github = Mock(spec=GitHub)
        result = apply_hierarchy(
            github,
            repo="x/y",
            scope="architectural",
            work_type="feature",
            parent=10,
            children=(),
            authorize_remote_mutation=True,
        )
        self.assertEqual(result.shape, ("epic", "feature", "task"))
        self.assertEqual(result.children, ())
        self.assertFalse(result.linked)
        github.api_graphql.assert_not_called()
        github.create_issue.assert_not_called()

    def test_bounded_bug_ignores_child_ceremony(self):
        github = Mock(spec=GitHub)
        result = apply_hierarchy(
            github,
            repo="x/y",
            scope="bounded",
            work_type="bug",
            parent=5,
            children=(6,),
            authorize_remote_mutation=True,
        )
        self.assertEqual(result.shape, ("bug",))
        self.assertEqual(result.children, ())
        self.assertFalse(result.linked)
        github.api_graphql.assert_not_called()
        github.create_issue.assert_not_called()

    def test_apply_hierarchy_persists_parent_and_children(self):
        github = Mock(spec=GitHub)
        github.api_graphql.return_value = {"data": {}}
        state = TaskState.new("task-1", "x/y")

        result = apply_hierarchy(
            github,
            repo="x/y",
            scope="architectural",
            work_type="feature",
            parent=10,
            children=(11,),
            authorize_remote_mutation=True,
            state=state,
        )

        self.assertEqual(result.parent, 10)
        self.assertEqual(result.children, (11,))
        self.assertFalse(result.linked)
        self.assertEqual(state.issue, 10)
        self.assertNotIn("parent_issue", state.to_dict())
        self.assertNotIn("child_issues", state.to_dict())

    def test_task_state_roundtrip_does_not_persist_hierarchy(self):
        github = Mock(spec=GitHub)
        state = TaskState.new("task-1", "x/y")
        apply_hierarchy(
            github,
            repo="x/y",
            scope="architectural",
            work_type="feature",
            parent=10,
            children=(11, 12),
            state=state,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            save_task_state(state, path)
            loaded = load_task_state(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("parent_issue", payload)
        self.assertNotIn("child_issues", payload)
        self.assertNotIn("parent_issue", loaded.to_dict())
        self.assertNotIn("child_issues", loaded.to_dict())
        self.assertEqual(loaded.issue, 10)

    def test_restart_recovers_hierarchy_from_github_shaped_input(self):
        recovered = recover_hierarchy(
            {
                "number": 10,
                "parent": {"number": 10},
                "subIssues": {"nodes": [{"number": 11}, {"number": 12}]},
            }
        )
        self.assertEqual(recovered.parent, 10)
        self.assertEqual(recovered.children, (11, 12))
        state = TaskState.new("task-1", "x/y")
        state.issue = recovered.parent
        self.assertEqual(state.to_dict().get("issue"), 10)
        self.assertNotIn("parent_issue", state.to_dict())
        self.assertNotIn("child_issues", state.to_dict())
