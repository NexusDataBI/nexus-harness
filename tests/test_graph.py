import unittest

from nexus_harness.graph import GraphNode, TaskGraph
from nexus_harness.state import StageStatus


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


if __name__ == "__main__":
    unittest.main()
