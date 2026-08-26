import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from nexus_harness.memory.guard import MemoryGuardError
from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.session import checkpoint_memory_candidates, session_recall
from nexus_harness.memory.store import init_project_memory, write_memory


def _verified_invariant(**overrides) -> MemoryDraft:
    payload = {
        "type": MemoryType.INVARIANT,
        "scope": MemoryScope.PROJECT,
        "project_id": "repo-1",
        "title": "Auth sessions stay isolated",
        "body": "Auth session cookies must stay isolated per tenant.",
        "sources": (MemorySource("approved_spec", "SPEC-AUTH"),),
        "related_paths": ("src/auth/**",),
        "tags": ("auth",),
    }
    payload.update(overrides)
    return MemoryDraft(**payload)


class MemorySessionTests(unittest.TestCase):
    def test_checkpoint_rejects_secret_in_draft_body(self):
        secret = "sk-abcdefghijklmnopqrstuvwxyz"
        draft = _verified_invariant(body=f"do not store {secret}")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scratch" / "candidates.json"
            with self.assertRaises(MemoryGuardError) as ctx:
                checkpoint_memory_candidates(path, [draft])
            message = str(ctx.exception)
            self.assertNotIn(secret, message)
            self.assertFalse(path.exists())

    def test_session_recall_degrades_on_corrupt_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            memory_id = "mem-invariant-corrupt-deadbeef"
            category = root / ".nexus" / "memory" / "invariants"
            (category / f"{memory_id}.md").write_text("# Corrupt\n", encoding="utf-8")
            (category / f"{memory_id}.json").write_text("{not-json", encoding="utf-8")

            try:
                capsule = session_recall(
                    root,
                    project_id="repo-1",
                    query="auth session",
                    affected_paths=("src/auth/session.py",),
                    cache_home=root / "cache",
                )
            except Exception as exc:
                self.fail(f"session_recall raised {type(exc).__name__}")
            self.assertEqual(capsule.hot, "")
            self.assertEqual(capsule.warm, "")
            self.assertEqual(capsule.item_count, 0)

    def test_session_recall_excludes_schema_invalid_missing_keys(self):
        secret = "schema-secret-must-not-echo"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            category = root / ".nexus" / "memory" / "invariants"
            memory_id = "mem-invariant-invalid-deadbeef"
            (category / f"{memory_id}.md").write_text(
                f"# Broken\n\n{secret}", encoding="utf-8"
            )
            (category / f"{memory_id}.json").write_text(
                '{"schema_version": 1, "id": "'
                + memory_id
                + '", "type": "invariant", "scope": "project", '
                '"project_id": "repo-1", "title": "Broken", "body": "' + secret + '"}',
                encoding="utf-8",
            )

            capsule = session_recall(
                root,
                project_id="repo-1",
                query="broken",
                cache_home=root / "cache",
            )

            self.assertEqual(capsule.hot, "")
            self.assertEqual(capsule.warm, "")
            self.assertTrue(capsule.findings)
            self.assertIn("excluded", capsule.warnings)
            self.assertNotIn(secret, capsule.warnings)

    def test_session_recall_excludes_schema_invalid_enum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            category = root / ".nexus" / "memory" / "invariants"
            memory_id = "mem-invariant-enum-deadbeef"
            (category / f"{memory_id}.md").write_text(
                "# Broken enum\n", encoding="utf-8"
            )
            (category / f"{memory_id}.json").write_text(
                '{"schema_version": 1, "id": "'
                + memory_id
                + '", "type": "not-a-type", "scope": "project", '
                '"project_id": "repo-1", "title": "Broken enum", "body": "bad", '
                '"status": "VERIFIED", "confidence": "HIGH", '
                '"created_at": "2026-08-25T00:00:00Z", "sensitivity": "PUBLIC"}',
                encoding="utf-8",
            )

            capsule = session_recall(
                root,
                project_id="repo-1",
                query="broken enum",
                cache_home=root / "cache",
            )

            self.assertEqual(capsule.item_count, 0)
            self.assertTrue(capsule.findings)
            self.assertIn("excluded", capsule.warnings)

    def test_session_recall_keeps_valid_memory_with_invalid_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            valid = write_memory(
                root,
                replace(
                    _verified_invariant().to_record(),
                    status=MemoryStatus.VERIFIED,
                    confidence=MemoryConfidence.HIGH,
                    verified_at="2026-08-25T00:00:00Z",
                ),
            )
            category = root / ".nexus" / "memory" / "invariants"
            invalid_id = "mem-invariant-invalid-sibling-deadbeef"
            (category / f"{invalid_id}.md").write_text(
                "# Invalid sibling\n\nNever inject this.", encoding="utf-8"
            )
            (category / f"{invalid_id}.json").write_text(
                '{"status": "NOT_A_STATUS", "body": "Never inject this."}',
                encoding="utf-8",
            )

            capsule = session_recall(
                root,
                project_id="repo-1",
                query="auth session",
                affected_paths=("src/auth/session.py",),
                cache_home=root / "cache",
            )

            self.assertIn(valid.id, capsule.hot)
            self.assertNotIn("Never inject this", capsule.hot)
            self.assertTrue(capsule.findings)

    def test_session_recall_puts_verified_invariant_in_hot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = write_memory(
                root,
                replace(
                    _verified_invariant().to_record(),
                    status=MemoryStatus.VERIFIED,
                    confidence=MemoryConfidence.HIGH,
                    verified_at="2026-08-25T00:00:00Z",
                ),
            )

            capsule = session_recall(
                root,
                project_id="repo-1",
                query="auth session",
                affected_paths=("src/auth/session.py",),
                cache_home=root / "cache",
            )
            self.assertIn(record.id, capsule.hot)
            self.assertIn(record.title, capsule.hot)
