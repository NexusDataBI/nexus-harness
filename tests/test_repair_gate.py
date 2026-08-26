import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from nexus_harness.hooks import dispatch
from nexus_harness.memory.guard import MemoryGuardError
from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.session import parse_contradictions, session_recall
from nexus_harness.memory.store import init_project_memory, read_memory, write_memory
from nexus_harness.pretool import evaluate_pretool
from nexus_harness.safe import PathSafetyError, reject_symlinks, verify_git_oid


class RepairGateTests(unittest.TestCase):
    def test_git_option_injection_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                verify_git_oid(Path(tmp), "--upload-pack=evil")
            with self.assertRaises(ValueError):
                verify_git_oid(Path(tmp), "-HEAD")

    def test_symlink_storage_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            linked = root / "linked"
            linked.symlink_to(real)
            with self.assertRaises(PathSafetyError):
                reject_symlinks(linked)

    def test_invalid_pretool_payload_fails_closed(self):
        code, output = evaluate_pretool({"tool_input": "not-a-dict"})
        self.assertEqual(code, 2)
        self.assertTrue(output["denied"])

    def test_secret_on_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = write_memory(
                root,
                MemoryDraft(
                    type=MemoryType.LESSON,
                    scope=MemoryScope.PROJECT,
                    project_id="repo-1",
                    title="Safe title",
                    body="Safe body",
                    sources=(MemorySource("review_finding", "rev-1"),),
                ).to_record(),
            )
            sidecar = next((root / ".nexus" / "memory" / "lessons").glob("*.json"))
            payload = sidecar.read_text(encoding="utf-8")
            sidecar.write_text(
                payload.replace("Safe body", "ghp_abcdefghijklmnopqrstuvwxyz01"),
                encoding="utf-8",
            )
            with self.assertRaises(MemoryGuardError):
                read_memory(root, record.id)

    def test_invalid_contradiction_item_does_not_drop_valid_items(self):
        valid = {
            "memory_id": "mem-1",
            "authority": "CURRENT_REPO",
            "pointer": "src/a.py",
        }
        items, findings = parse_contradictions([valid, "not-an-object", 3])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].memory_id, "mem-1")
        self.assertGreaterEqual(len(findings), 1)

    def test_invalid_contradictions_do_not_wipe_capsule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            write_memory(
                root,
                replace(
                    MemoryDraft(
                        type=MemoryType.INVARIANT,
                        scope=MemoryScope.PROJECT,
                        project_id="repo",
                        title="Keep this",
                        body="CAPSULE-BODY-MUST-REMAIN",
                        sources=(MemorySource("approved_spec", "SPEC-1"),),
                    ).to_record(),
                    status=MemoryStatus.VERIFIED,
                    confidence=MemoryConfidence.HIGH,
                    verified_at="2026-08-25T00:00:00Z",
                ),
            )
            capsule = session_recall(
                root,
                project_id="repo",
                query="keep this",
                cache_home=Path(tmp) / "cache",
                contradictions=["bogus", {"memory_id": "missing"}],
            )
        self.assertIn("CAPSULE-BODY-MUST-REMAIN", capsule.text)
        self.assertTrue(
            any(
                finding["code"] == "invalid_contradiction"
                for finding in capsule.findings
            )
        )

    def test_classification_fingerprint_skips_repeat_recall(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "project_root": tmp,
                "repo_id": "repo",
                "task_id": "task",
                "query": "same question",
            }
            with patch.dict(os.environ, {"NEXUS_RUNTIME_HOME": tmp}):
                first = dispatch("UserPromptSubmit", payload)
                second = dispatch("UserPromptSubmit", payload)
        self.assertTrue(first.output["refreshed"])
        self.assertEqual(second.output, {"refreshed": False})


if __name__ == "__main__":
    unittest.main()
