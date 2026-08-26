import tempfile
import unittest
from pathlib import Path

from nexus_harness.runtime_codex import render


class CodexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.files = {
            item.relative_path: item.content.decode("utf-8")
            for item in render(Path("."))
        }

    def test_codex_output_has_no_claude_env_or_project_path(self):
        text = "\n".join(self.files.values())
        self.assertNotIn("CLAUDE_CODE_", text)
        self.assertNotIn("Automacao-Vuca", text)
        self.assertNotIn("Sonnet", text)
        self.assertNotIn("/Users/", text)

    def test_codex_output_is_minimal_and_canonical(self):
        self.assertEqual(set(self.files), {"AGENTS.md", "codex/config.toml"})
        agents = self.files["AGENTS.md"]
        self.assertIn("NEXUS WORKFLOW IS MANDATORY", agents)
        self.assertIn("Nexus Harness", agents)
        self.assertIn("Nexus Memory", agents)
        self.assertIn("completion gate", agents.lower())
        self.assertIn("session_recall", agents)
        self.assertIn("checkpoint_memory_candidates", agents)
        self.assertIn("restore_memory_candidates", agents)

    def test_codex_config_has_safe_defaults_and_neutral_paths(self):
        config = self.files["codex/config.toml"]
        self.assertIn("sandbox", config)
        self.assertIn("approval", config)
        self.assertIn("sandbox_mode", config)
        self.assertNotIn('paths = ["./plugins"]', config)
        self.assertIn("workspace", config)
        self.assertNotIn("trust", config.lower())
        self.assertNotIn("model", config.lower())

    def test_codex_prefers_constitution_under_render_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "core" / "constitution.md").write_text(
                "CUSTOM CONSTITUTION", encoding="utf-8"
            )
            files = {
                item.relative_path: item.content.decode("utf-8")
                for item in render(root)
            }
        self.assertIn("CUSTOM CONSTITUTION", files["AGENTS.md"])


if __name__ == "__main__":
    unittest.main()
