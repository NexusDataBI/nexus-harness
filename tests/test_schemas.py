import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATES = {
    "PENDING",
    "PASS",
    "FAIL",
    "SKIP",
    "BLOCKED",
    "WAITING_APPROVAL",
}
NODE_FIELDS = {
    "id",
    "stage",
    "kind",
    "dependencies",
    "reads",
    "writes",
    "affected_paths",
    "risk",
    "execution_target",
    "estimated_cost",
    "status",
    "evidence_outputs",
}
STAGES = {str(stage) for stage in range(10)}


def load_schema(relative_path):
    with (ROOT / relative_path).open(encoding="utf-8") as schema_file:
        return json.load(schema_file)


def accepts_object_contract(document, schema):
    required = set(schema.get("required", []))
    properties = set(schema.get("properties", {}))
    keys = set(document)
    return required <= keys and (
        schema.get("additionalProperties", True) or keys <= properties
    )


class SchemaContractTests(unittest.TestCase):
    def test_graph_node_rejects_incomplete_and_accepts_complete_minimal_document(self):
        node_schema = load_schema("core/graph/graph.schema.json")["$defs"]["node"]
        complete_node = {
            "id": "task-1",
            "stage": 0,
            "kind": "implementation",
            "dependencies": [],
            "reads": [],
            "writes": [],
            "affected_paths": [],
            "risk": "low",
            "execution_target": "local",
            "estimated_cost": 0,
            "status": "PENDING",
            "evidence_outputs": [],
        }

        self.assertEqual(set(node_schema["required"]), NODE_FIELDS)
        self.assertEqual(set(node_schema["properties"]), NODE_FIELDS)
        self.assertFalse(node_schema["additionalProperties"])
        self.assertEqual(set(node_schema["properties"]["status"]["enum"]), STATES)
        self.assertFalse(accepts_object_contract({"id": "task-1"}, node_schema))
        self.assertTrue(accepts_object_contract(complete_node, node_schema))

    def test_stage_status_rejects_incomplete_and_accepts_complete_minimal_document(
        self,
    ):
        task_state_schema = load_schema("core/workflow/task-state.schema.json")
        stage_schema = task_state_schema["properties"]["stage_status"]
        complete_status = {stage: "PENDING" for stage in STAGES}

        self.assertEqual(set(stage_schema["required"]), STAGES)
        self.assertEqual(set(stage_schema["properties"]), STAGES)
        self.assertFalse(stage_schema["additionalProperties"])
        self.assertFalse(accepts_object_contract({}, stage_schema))
        self.assertTrue(accepts_object_contract(complete_status, stage_schema))
        for stage in STAGES:
            self.assertEqual(
                stage_schema["properties"][stage]["$ref"], "#/$defs/stageState"
            )
        self.assertEqual(set(task_state_schema["$defs"]["stageState"]["enum"]), STATES)


if __name__ == "__main__":
    unittest.main()
