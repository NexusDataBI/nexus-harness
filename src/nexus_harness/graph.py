from dataclasses import dataclass, replace

from nexus_harness.state import StageStatus

_READY_DEPENDENCY_STATUSES = frozenset({StageStatus.PASS, StageStatus.SKIP})


def _as_tuple(value) -> tuple:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _normalize_write_path(path: str) -> str:
    return path.rstrip("/")


def _paths_overlap(left: str, right: str) -> bool:
    left = _normalize_write_path(left)
    right = _normalize_write_path(right)
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "stage": self.stage,
            "kind": self.kind,
            "dependencies": list(self.depends_on),
            "reads": list(self.reads),
            "writes": list(self.writes),
            "affected_paths": list(self.affected_paths),
            "risk": self.risk,
            "execution_target": self.execution_target,
            "estimated_cost": self.estimated_cost,
            "status": str(self.status),
            "evidence_outputs": list(self.evidence_outputs),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "GraphNode":
        dependencies = payload.get("dependencies")
        if dependencies is None:
            dependencies = payload.get("depends_on", ())
        return cls(
            id=payload["id"],
            stage=payload.get("stage", 0),
            kind=payload.get("kind", ""),
            depends_on=dependencies,
            reads=payload.get("reads", ()),
            writes=payload.get("writes", ()),
            affected_paths=payload.get("affected_paths", ()),
            execution_target=payload.get("execution_target", "local"),
            risk=payload.get("risk", "low"),
            estimated_cost=payload.get("estimated_cost", 0),
            status=payload.get("status", StageStatus.PENDING),
            evidence_outputs=payload.get("evidence_outputs", ()),
        )


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
        ready_ids = {node.id for node in ready}
        conflicting_ids = {
            node_id
            for left, right in self.conflicts()
            if left in ready_ids and right in ready_ids
            for node_id in (left, right)
        }
        return [node for node in ready if node.id not in conflicting_ids]

    def conflicts(self) -> set[tuple[str, str]]:
        writers: dict[str, set[str]] = {}
        for node in self._nodes.values():
            for path in node.writes:
                writers.setdefault(_normalize_write_path(path), set()).add(node.id)
        pairs: set[tuple[str, str]] = set()
        paths = sorted(writers)
        for index, left_path in enumerate(paths):
            for right_path in paths[index:]:
                if not _paths_overlap(left_path, right_path):
                    continue
                node_ids = sorted(writers[left_path] | writers[right_path])
                for left_index, left in enumerate(node_ids):
                    for right in node_ids[left_index + 1 :]:
                        pairs.add((left, right))
        return pairs

    def invalidate(self, changed_paths) -> None:
        changed = set(changed_paths)
        reset = {
            node_id
            for node_id, node in self._nodes.items()
            if changed.intersection(node.affected_paths)
        }
        growing = True
        while growing:
            growing = False
            for node_id, node in self._nodes.items():
                if node_id in reset:
                    continue
                if node.status not in _READY_DEPENDENCY_STATUSES:
                    continue
                if any(dependency in reset for dependency in node.depends_on):
                    reset.add(node_id)
                    growing = True
        updated = {}
        for node_id, node in self._nodes.items():
            if node_id in reset:
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
