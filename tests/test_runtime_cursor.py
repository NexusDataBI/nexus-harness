import json
import tempfile
import unittest
from pathlib import Path

from nexus_harness.runtime_cursor import render


class CursorAdapterTests(unittest.TestCase):
    def test_cursor_sandbox_is_not_disabled(self):
        files = {item.relative_path: item.content for item in render(Path("."))}
        sandbox = json.loads(files["cursor/sandbox.json"])
        self.assertEqual(sandbox["type"], "workspace_readwrite")
        self.assertEqual(sandbox["networkPolicy"]["default"], "deny")
        self.assertEqual(sandbox["networkPolicy"]["allowedHosts"], [])
        self.assertNotIn("disabled", sandbox)

    def test_cursor_rules_are_minimal_and_runtime_neutral(self):
        files = {
            item.relative_path: item.content.decode() for item in render(Path("."))
        }
        self.assertEqual(
            set(files),
            {
                "USER_RULES.md",
                ".cursor/rules/nexus-workflow.mdc",
                "cursor/sandbox.json",
            },
        )
        output = "\n".join(files.values()).lower()
        self.assertIn("nexus memory", output)
        self.assertIn("completion gate", output)
        self.assertIn("session_recall", output)
        self.assertNotIn(".cursor/memory", output)
        self.assertNotIn("auto-deploy", output)
        self.assertNotIn("model", output)

    def test_project_profile_can_allow_only_explicit_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "profiles").mkdir()
            (root / "profiles" / "active.toml").write_text(
                '[network]\nallowed_hosts = ["registry.example.test", "api.example.test"]\n',
                encoding="utf-8",
            )
            files = {item.relative_path: item.content for item in render(root)}
        sandbox = json.loads(files["cursor/sandbox.json"])
        self.assertEqual(
            sandbox["networkPolicy"]["allowedHosts"],
            ["api.example.test", "registry.example.test"],
        )

    def test_generated_output_has_no_machine_or_memory_leakage(self):
        files = {
            item.relative_path: item.content.decode() for item in render(Path("."))
        }
        output = "\n".join(files.values()).lower()
        for forbidden in ("/users/", "ssh ", "raw memory", "claude-mem"):
            self.assertNotIn(forbidden, output)
