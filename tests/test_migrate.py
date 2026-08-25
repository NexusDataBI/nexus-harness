import tempfile
import unittest
from pathlib import Path

from nexus_harness.migrate import apply_cleanup, cleanup_plan


class MigrationTests(unittest.TestCase):
    def test_cleanup_plan_marks_appledouble_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "._junk"
            target.write_text("x", encoding="utf-8")
            plan = cleanup_plan(root)
            self.assertEqual(plan[0]["action"], "delete")
            self.assertTrue(target.exists())

    def test_apply_cleanup_rejects_path_outside_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outsider = Path(tmp).resolve().parent / "outside-cleanup-target"
            plan = [
                {
                    "action": "delete",
                    "path": str(outsider),
                    "reason": "appledouble",
                }
            ]
            with self.assertRaises(ValueError) as raised:
                apply_cleanup(plan, root)
            self.assertIn("outside", str(raised.exception).lower())

    def test_apply_cleanup_refuses_frozen_v3_export_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "v3-export"
            root.mkdir()
            target = root / "._junk"
            target.write_text("x", encoding="utf-8")
            plan = cleanup_plan(root)
            with self.assertRaises(ValueError) as raised:
                apply_cleanup(plan, root)
            self.assertIn("v3-export", str(raised.exception).lower())
            self.assertTrue(target.exists())

    def test_apply_cleanup_deletes_appledouble_in_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "._junk"
            target.write_text("x", encoding="utf-8")
            plan = cleanup_plan(root)
            apply_cleanup(plan, root)
            self.assertFalse(target.exists())

    def test_cleanup_plan_marks_bak_and_circuit_breaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bak = root / "stale.bak"
            bak.write_text("old", encoding="utf-8")
            status = root / "harness-sync" / "status.json"
            status.parent.mkdir(parents=True)
            status.write_text(
                '{"reason": "circuit-breaker", "status": "blocked"}',
                encoding="utf-8",
            )
            log = root / "harness-sync" / "sync.log"
            log.write_text("blocked", encoding="utf-8")
            keep = root / "harness-sync" / "coordinator.py"
            keep.write_text("source", encoding="utf-8")

            plan = cleanup_plan(root)
            paths = {item["path"] for item in plan}

            self.assertIn("stale.bak", paths)
            self.assertIn("harness-sync/status.json", paths)
            self.assertIn("harness-sync/sync.log", paths)
            self.assertNotIn("harness-sync/coordinator.py", paths)
            self.assertTrue(bak.exists())
            self.assertTrue(status.exists())
            self.assertTrue(log.exists())

    def test_cleanup_plan_marks_generated_skill_copies_not_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "skills/foo/SKILL.md": "same",
                "claude/skills/foo/SKILL.md": "same",
                "agents-skills/foo/SKILL.md": "same",
                "skills/bar/SKILL.md": "unique",
            }
            for rel, text in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

            plan = cleanup_plan(root)
            paths = {item["path"] for item in plan}

            self.assertIn("claude/skills/foo/SKILL.md", paths)
            self.assertIn("agents-skills/foo/SKILL.md", paths)
            self.assertNotIn("skills/foo/SKILL.md", paths)
            self.assertNotIn("skills/bar/SKILL.md", paths)
            self.assertTrue((root / "skills/foo/SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
