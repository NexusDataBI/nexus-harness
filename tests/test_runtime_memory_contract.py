import unittest
from pathlib import Path

from nexus_harness.adapters import render_all


ROOT = Path(__file__).resolve().parents[1]


class RuntimeMemoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {
            item.relative_path: item.content.decode("utf-8")
            for item in render_all(ROOT)
        }
        cls.output = "\n".join(cls.files.values()).lower()

    def test_all_runtimes_use_nexus_memory_public_apis(self):
        for runtime_text in (
            self.files["claude/CLAUDE.md"],
            self.files["USER_RULES.md"],
            self.files["AGENTS.md"],
            self.files[".cursor/rules/nexus-workflow.mdc"],
        ):
            self.assertIn("nexus memory", runtime_text.lower())
            self.assertIn("nexus_harness.memory", runtime_text)
            self.assertIn("session_recall", runtime_text)

    def test_generated_output_has_no_paths_bodies_or_runtime_memory_stores(self):
        forbidden = (
            "/users/",
            "~/nexusmemory",
            "auth session cookies",
            "claude-mem",
            "chroma",
            "qdrant",
            "pinecone",
            "embedding",
            ".cursor/memory",
            "sqlite",
            "memory.db",
        )
        for value in forbidden:
            self.assertNotIn(value, self.output)

    def test_candidate_stale_and_confidential_memory_are_not_auto_injected(self):
        self.assertIn(
            "candidate, stale, invalid, or confidential memory is not automatically injected",
            self.output,
        )

    def test_generated_output_has_no_project_or_runtime_leakage(self):
        for value in (
            "claude-sonnet",
            "automacao-vuca",
            "claude_code_",
            "ssh ",
        ):
            self.assertNotIn(value, self.output)

    def test_generated_output_has_no_second_canonical_memory_database(self):
        for value in ("memory store", "canonical database", "memory database"):
            self.assertNotIn(value, self.output)


if __name__ == "__main__":
    unittest.main()
