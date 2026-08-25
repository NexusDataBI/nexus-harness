import json
import tempfile
import unittest
from pathlib import Path
from nexus_harness.skills import (
    build_skill_ledger,
    discover_skill_files,
    group_exact_duplicates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class SkillTests(unittest.TestCase):
    def test_groups_identical_skill_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("a/foo/SKILL.md", "b/foo/SKILL.md", "c/bar/SKILL.md"):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("same" if "foo" in rel else "other", encoding="utf-8")
            files = discover_skill_files(root)
            groups = group_exact_duplicates(files)
            self.assertEqual(sorted(len(group) for group in groups), [2])

    def test_ledger_groups_by_name_and_marks_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "agents-skills/nexus-frontend/SKILL.md": "same",
                "claude/skills/nexus-frontend/SKILL.md": "same",
                "claude/skills/handoff/SKILL.md": "only",
                "agents-skills/impeccable/SKILL.md": "v1",
                "cursor/skills/impeccable/SKILL.md": "v2",
            }
            for rel, text in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

            ledger = build_skill_ledger(root)
            by_name = {entry["name"]: entry for entry in ledger}

            self.assertEqual([entry["name"] for entry in ledger], sorted(by_name))
            frontend = by_name["nexus-frontend"]
            self.assertEqual(frontend["relationship"], "exact_duplicate")
            self.assertEqual(frontend["decision"], "canonicalize")
            self.assertEqual(
                frontend["sources"],
                [
                    "agents-skills/nexus-frontend/SKILL.md",
                    "claude/skills/nexus-frontend/SKILL.md",
                ],
            )
            self.assertEqual(frontend["target"], "skills/nexus-frontend/SKILL.md")

            handoff = by_name["handoff"]
            self.assertEqual(handoff["relationship"], "unique")
            self.assertEqual(handoff["decision"], "merge")
            self.assertEqual(handoff["sources"], ["claude/skills/handoff/SKILL.md"])

            impeccable = by_name["impeccable"]
            self.assertEqual(impeccable["relationship"], "divergent")
            self.assertEqual(impeccable["decision"], "upstream")
            self.assertIn("rationale", impeccable)
            self.assertEqual(len(impeccable["sources"]), 2)

    def test_obsolete_unique_skill_emits_null_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "claude/scheduled-tasks/babysitting-prs/SKILL.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("scheduled task", encoding="utf-8")

            ledger = build_skill_ledger(root)
            entry = next(item for item in ledger if item["name"] == "babysitting-prs")

            self.assertEqual(entry["decision"], "obsolete")
            self.assertEqual(entry["relationship"], "unique")
            self.assertIn("target", entry)
            self.assertIsNone(entry["target"])

    def test_committed_skill_ledger_has_target_on_every_entry(self):
        ledger_path = REPO_ROOT / "docs/migration/skill-ledger.json"
        with ledger_path.open(encoding="utf-8") as handle:
            ledger = json.load(handle)

        self.assertGreater(len(ledger), 0)
        for entry in ledger:
            self.assertIn("target", entry, msg=f"missing target on {entry['name']}")
