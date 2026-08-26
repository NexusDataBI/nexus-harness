import json
import unittest
from pathlib import Path

from nexus_harness.graph import GraphNode, TaskGraph
from nexus_harness.state import StageStatus

_GRAPH_NODE_SCHEMA = json.loads(
    Path("core/graph/graph.schema.json").read_text(encoding="utf-8")
)["$defs"]["node"]


class GraphTests(unittest.TestCase):
    def test_independent_nodes_are_ready_together(self):
        graph = TaskGraph(
            [
                GraphNode(
                    "backend", reads=("shared/schema.ts",), writes=("apps/server/a.ts",)
                ),
                GraphNode(
                    "frontend", reads=("shared/schema.ts",), writes=("apps/web/a.ts",)
                ),
            ]
        )
        self.assertEqual({n.id for n in graph.ready_nodes()}, {"backend", "frontend"})

    def test_writers_of_same_resource_conflict(self):
        graph = TaskGraph(
            [
                GraphNode("a", writes=("shared/schema.ts",)),
                GraphNode("b", writes=("shared/schema.ts",)),
            ]
        )
        self.assertEqual(graph.conflicts(), {("a", "b")})

    def test_parent_and_child_write_paths_conflict(self):
        graph = TaskGraph(
            [
                GraphNode("parent", writes=("src/auth",)),
                GraphNode("child", writes=("src/auth/session.py",)),
            ]
        )
        self.assertEqual(graph.conflicts(), {("child", "parent")})

    def test_trailing_slash_parent_write_path_conflicts(self):
        graph = TaskGraph(
            [
                GraphNode("parent", writes=("src/auth/",)),
                GraphNode("child", writes=("src/auth/session.py",)),
            ]
        )
        self.assertEqual(graph.conflicts(), {("child", "parent")})

    def test_similar_but_non_overlapping_write_paths_do_not_conflict(self):
        graph = TaskGraph(
            [
                GraphNode("a", writes=("src/aut",)),
                GraphNode("b", writes=("src/auth.py",)),
            ]
        )
        self.assertEqual(graph.conflicts(), set())

    def test_conflicting_ready_writers_are_excluded_fail_closed(self):
        graph = TaskGraph(
            [
                GraphNode("parent", writes=("src/auth",)),
                GraphNode("child", writes=("src/auth/session.py",)),
            ]
        )
        self.assertEqual(graph.ready_nodes(), [])

    def test_independent_ready_writers_remain_ready_together(self):
        graph = TaskGraph(
            [
                GraphNode("a", writes=("src/a.py",)),
                GraphNode("b", writes=("src/b.py",)),
            ]
        )
        self.assertEqual({n.id for n in graph.ready_nodes()}, {"a", "b"})

    def test_rejects_cycles(self):
        with self.assertRaises(ValueError):
            TaskGraph(
                [
                    GraphNode("a", depends_on=("b",)),
                    GraphNode("b", depends_on=("a",)),
                ]
            )

    def test_rejects_missing_dependency_ids(self):
        with self.assertRaises(ValueError):
            TaskGraph(
                [
                    GraphNode("a", depends_on=("missing",)),
                ]
            )

    def test_dependent_node_not_ready_until_deps_pass_or_skip(self):
        pending = TaskGraph(
            [
                GraphNode("base"),
                GraphNode("app", depends_on=("base",)),
            ]
        )
        self.assertEqual({n.id for n in pending.ready_nodes()}, {"base"})

        failed = TaskGraph(
            [
                GraphNode("base", status=StageStatus.FAIL),
                GraphNode("app", depends_on=("base",)),
            ]
        )
        self.assertEqual({n.id for n in failed.ready_nodes()}, set())

        passed = TaskGraph(
            [
                GraphNode("base", status=StageStatus.PASS),
                GraphNode("app", depends_on=("base",)),
            ]
        )
        self.assertEqual({n.id for n in passed.ready_nodes()}, {"app"})

        skipped = TaskGraph(
            [
                GraphNode("base", status=StageStatus.SKIP),
                GraphNode("app", depends_on=("base",)),
            ]
        )
        self.assertEqual({n.id for n in skipped.ready_nodes()}, {"app"})

    def test_invalidate_resets_overlapping_nodes_and_clears_evidence(self):
        graph = TaskGraph(
            [
                GraphNode(
                    "hit",
                    affected_paths=("apps/server/a.ts",),
                    status=StageStatus.PASS,
                    evidence_outputs=("ev-1",),
                ),
                GraphNode(
                    "miss",
                    affected_paths=("apps/web/b.ts",),
                    status=StageStatus.PASS,
                    evidence_outputs=("ev-2",),
                ),
            ]
        )
        graph.invalidate(("apps/server/a.ts",))
        hit = graph.get("hit")
        miss = graph.get("miss")
        self.assertEqual(hit.status, StageStatus.PENDING)
        self.assertEqual(tuple(hit.evidence_outputs), ())
        self.assertEqual(miss.status, StageStatus.PASS)
        self.assertEqual(tuple(miss.evidence_outputs), ("ev-2",))

    def test_invalidate_cascades_to_pass_dependents(self):
        graph = TaskGraph(
            [
                GraphNode(
                    "a",
                    affected_paths=("apps/server/a.ts",),
                    status=StageStatus.PASS,
                    evidence_outputs=("ev-1",),
                ),
                GraphNode(
                    "b",
                    depends_on=("a",),
                    status=StageStatus.PASS,
                    evidence_outputs=("ev-2",),
                ),
            ]
        )
        graph.invalidate(("apps/server/a.ts",))
        first = graph.get("a")
        dependent = graph.get("b")
        self.assertEqual(first.status, StageStatus.PENDING)
        self.assertEqual(dependent.status, StageStatus.PENDING)
        self.assertEqual(tuple(first.evidence_outputs), ())
        self.assertEqual(tuple(dependent.evidence_outputs), ())

    def test_graph_node_to_dict_uses_schema_dependencies(self):
        node = GraphNode(
            "a",
            stage=1,
            kind="implementation",
            depends_on=("b",),
            reads=("r.ts",),
            writes=("w.ts",),
            affected_paths=("w.ts",),
            risk="medium",
            execution_target="local",
            estimated_cost=1.5,
            status=StageStatus.PASS,
            evidence_outputs=("ev-1",),
        )
        payload = node.to_dict()
        self.assertIn("dependencies", payload)
        self.assertNotIn("depends_on", payload)
        self.assertTrue(set(_GRAPH_NODE_SCHEMA["required"]) <= set(payload))
        self.assertEqual(payload["dependencies"], ["b"])
        restored = GraphNode.from_dict(payload)
        self.assertEqual(restored.depends_on, ("b",))
        self.assertEqual(restored.id, "a")
        self.assertEqual(restored.status, StageStatus.PASS)
        self.assertEqual(restored.evidence_outputs, ("ev-1",))

    def test_graph_node_from_dict_accepts_depends_on_or_dependencies(self):
        from_schema = GraphNode.from_dict({"id": "a", "dependencies": ["b"]})
        from_python = GraphNode.from_dict({"id": "a", "depends_on": ["c"]})
        self.assertEqual(from_schema.depends_on, ("b",))
        self.assertEqual(from_python.depends_on, ("c",))


if __name__ == "__main__":
    unittest.main()
