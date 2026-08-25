import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from nexus_harness.memory.models import (
    MemoryDraft,
    MemoryScope,
    MemorySource,
    MemoryType,
)
from nexus_harness.memory.store import (
    CATEGORY_BY_TYPE,
    MemoryStoreError,
    init_project_memory,
    load_project_memories,
    read_memory,
    write_memory,
)


def _component_draft(**overrides) -> MemoryDraft:
    payload = {
        "type": MemoryType.COMPONENT,
        "scope": MemoryScope.PROJECT,
        "project_id": "repo-1",
        "title": "API owns lead state",
        "body": "The API is authoritative for persisted lead state.",
    }
    payload.update(overrides)
    return MemoryDraft(**payload)


class MemoryStoreTests(unittest.TestCase):
    def test_write_creates_markdown_and_json_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            draft = _component_draft()
            record = write_memory(root, draft.to_record())
            category = root / ".nexus" / "memory" / "components"
            self.assertTrue((category / f"{record.id}.md").exists())
            self.assertTrue((category / f"{record.id}.json").exists())
            self.assertEqual(read_memory(root, record.id), record)

    def test_init_is_idempotent_and_preserves_unknown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = init_project_memory(root)
            extra = first / "user-notes.md"
            extra.write_text("keep this file\n", encoding="utf-8")
            stray = first / "components" / "manual-note.txt"
            stray.write_text("also keep\n", encoding="utf-8")
            second = init_project_memory(root)
            self.assertEqual(first, second)
            self.assertEqual(first, root / ".nexus" / "memory")
            self.assertTrue(extra.exists())
            self.assertEqual(extra.read_text(encoding="utf-8"), "keep this file\n")
            self.assertTrue(stray.exists())
            self.assertEqual(stray.read_text(encoding="utf-8"), "also keep\n")
            for category in CATEGORY_BY_TYPE.values():
                self.assertTrue((first / category).is_dir())
            self.assertTrue((first / "README.md").is_file())

    def test_init_readme_matches_harness_template(self):
        template = Path("templates/memory/project-memory/README.md")
        self.assertTrue(template.is_file())
        expected = template.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory_root = init_project_memory(root)
            self.assertEqual(
                (memory_root / "README.md").read_text(encoding="utf-8"),
                expected,
            )

    def test_writes_each_type_to_mapped_category(self):
        expected = {
            MemoryType.DECISION: "decisions",
            MemoryType.INVARIANT: "invariants",
            MemoryType.COMPONENT: "components",
            MemoryType.PATTERN: "patterns",
            MemoryType.LESSON: "lessons",
            MemoryType.INCIDENT: "incidents",
        }
        self.assertEqual(CATEGORY_BY_TYPE, expected)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            for memory_type, category in expected.items():
                record = write_memory(
                    root,
                    _component_draft(
                        type=memory_type,
                        title=f"{memory_type.value} title",
                        body=f"{memory_type.value} body",
                    ).to_record(),
                )
                folder = root / ".nexus" / "memory" / category
                self.assertTrue((folder / f"{record.id}.md").exists())
                self.assertTrue((folder / f"{record.id}.json").exists())

    def test_markdown_has_pointers_not_json_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            draft = _component_draft(
                sources=(MemorySource(kind="adr", ref="ADR-014"),),
            )
            record = write_memory(root, draft.to_record())
            markdown = (
                root / ".nexus" / "memory" / "components" / f"{record.id}.md"
            ).read_text(encoding="utf-8")
            self.assertIn(f"# {record.title}", markdown)
            self.assertIn(record.body, markdown)
            self.assertIn("## Nexus Memory", markdown)
            self.assertIn(record.id, markdown)
            self.assertIn(record.status.value, markdown)
            self.assertIn(record.type.value, markdown)
            self.assertIn("ADR-014", markdown)
            self.assertNotIn('"schema_version"', markdown)
            self.assertNotIn(json.dumps(record.to_json_dict()), markdown)

    def test_duplicate_id_with_different_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = write_memory(root, _component_draft().to_record())
            changed = replace(record, body="A different durable fact.")
            with self.assertRaises(MemoryStoreError):
                write_memory(root, changed)
            self.assertEqual(read_memory(root, record.id), record)

    def test_identical_rewrite_is_allowed_without_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = write_memory(root, _component_draft().to_record())
            again = write_memory(root, record)
            self.assertEqual(again, record)
            self.assertEqual(read_memory(root, record.id), record)

    def test_replace_requires_stable_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = write_memory(root, _component_draft().to_record())
            updated = replace(record, body="Updated component fact.")
            written = write_memory(root, updated, replace=True)
            self.assertEqual(written.body, "Updated component fact.")
            moved = replace(updated, type=MemoryType.DECISION)
            with self.assertRaises(MemoryStoreError):
                write_memory(root, moved, replace=True)
            self.assertEqual(read_memory(root, record.id).type, MemoryType.COMPONENT)

    def test_load_project_memories_is_sorted_and_ignores_tmp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            first = write_memory(
                root,
                _component_draft(title="Alpha component").to_record(),
            )
            second = write_memory(
                root,
                _component_draft(
                    type=MemoryType.LESSON,
                    title="Beta lesson",
                    body="A reusable lesson.",
                ).to_record(),
            )
            stray = root / ".nexus" / "memory" / "components" / "zzz.json.tmp"
            stray.write_text('{"id":"not-loaded"}', encoding="utf-8")
            loaded = load_project_memories(root)
            self.assertEqual(loaded, sorted((first, second), key=lambda item: item.id))

    def test_read_memory_requires_exactly_one_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            with self.assertRaises(MemoryStoreError) as ctx:
                read_memory(root, "mem-component-missing-deadbeef")
            self.assertIn("expected exactly one sidecar", str(ctx.exception))

    def test_failed_second_temp_write_does_not_publish_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = _component_draft().to_record()
            from nexus_harness.memory import store as store_mod

            original = store_mod._write_temp_file
            calls = {"count": 0}

            def fail_second(path: Path, data: str) -> None:
                calls["count"] += 1
                if calls["count"] >= 2:
                    raise OSError("simulated write failure")
                original(path, data)

            with patch.object(store_mod, "_write_temp_file", side_effect=fail_second):
                with self.assertRaises(OSError):
                    write_memory(root, record)

            category = root / ".nexus" / "memory" / "components"
            self.assertFalse((category / f"{record.id}.md").exists())
            self.assertFalse((category / f"{record.id}.json").exists())
            self.assertFalse((category / f"{record.id}.md.tmp").exists())
            self.assertFalse((category / f"{record.id}.json.tmp").exists())
            with self.assertRaises(MemoryStoreError):
                read_memory(root, record.id)
