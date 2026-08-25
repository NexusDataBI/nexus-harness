from dataclasses import dataclass, replace

from nexus_harness.state import StageStatus

_READY_DEPENDENCY_STATUSES = frozenset({StageStatus.PASS, StageStatus.SKIP})


def _as_tuple(value) -> tuple:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


@dataclass(frozen=True)
class GraphNode:
    id: str
    stage: int = 0
    kind: str = ""
    depends_on: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    affected_paths: tuple[str, ...] = ()
    execution_target: str = "local"
    risk: str = "low"
    estimated_cost: float = 0
    status: StageStatus = StageStatus.PENDING
    evidence_outputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "depends_on", _as_tuple(self.depends_on))
        object.__setattr__(self, "reads", _as_tuple(self.reads))
        object.__setattr__(self, "writes", _as_tuple(self.writes))
        object.__setattr__(self, "affected_paths", _as_tuple(self.affected_paths))
        object.__setattr__(self, "evidence_outputs", _as_tuple(self.evidence_outputs))
        if not isinstance(self.status, StageStatus):
            object.__setattr__(self, "status", StageStatus(self.status))


class TaskGraph:
    def __init__(self, nodes) -> None:
        indexed: dict[str, GraphNode] = {}
        for node in nodes:
            if node.id in indexed:
                raise ValueError(f"duplicate node id: {node.id}")
            indexed[node.id] = node
        for node in indexed.values():
            for dependency in node.depends_on:
                if dependency not in indexed:
                    raise ValueError(f"missing dependency id: {dependency}")
        self._assert_acyclic(indexed)
        self._nodes = indexed

    def get(self, node_id: str) -> GraphNode:
        return self._nodes[node_id]

    def ready_nodes(self) -> list[GraphNode]:
        ready = []
        for node in self._nodes.values():
            if node.status is not StageStatus.PENDING:
                continue
            if all(
                self._nodes[dependency].status in _READY_DEPENDENCY_STATUSES
                for dependency in node.depends_on
            ):
                ready.append(node)
        return ready

    def conflicts(self) -> set[tuple[str, str]]:
        writers: dict[str, list[str]] = {}
        for node in self._nodes.values():
            for path in node.writes:
                writers.setdefault(path, []).append(node.id)
        pairs: set[tuple[str, str]] = set()
        for node_ids in writers.values():
            unique = sorted(set(node_ids))
            for index, left in enumerate(unique):
                for right in unique[index + 1 :]:
                    pairs.add((left, right))
        return pairs

    def invalidate(self, changed_paths) -> None:
        changed = set(changed_paths)
        updated = {}
        for node_id, node in self._nodes.items():
            if changed.intersection(node.affected_paths):
                updated[node_id] = replace(
                    node,
                    status=StageStatus.PENDING,
                    evidence_outputs=(),
                )
            else:
                updated[node_id] = node
        self._nodes = updated

    @staticmethod
    def _assert_acyclic(indexed: dict[str, GraphNode]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError(f"cycle involving {node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in indexed[node_id].depends_on:
                walk(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in indexed:
            walk(node_id)
