import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryRecord,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.portfolio import (
    ProjectBridge,
    init_portfolio_vault,
    load_portfolio_memories,
    write_project_bridge,
)
from nexus_harness.memory.retrieval import MemoryQueryContext, search_memory
from nexus_harness.memory.store import (
    MemoryStoreError,
    init_project_memory,
    write_memory,
)

_TEMPLATE_DIR = Path("templates/memory/portfolio-vault")
_VAULT_DIRS = (
    "projects",
    "domains",
    "patterns",
    "lessons",
    "decisions",
    "incidents",
)


def _verified_project(title: str) -> MemoryRecord:
    return replace(
        MemoryDraft(
            type=MemoryType.LESSON,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title=title,
            body="Project-scoped recall control.",
            sources=(MemorySource("approved_spec", "SPEC-1"),),
        ).to_record(),
        status=MemoryStatus.VERIFIED,
        confidence=MemoryConfidence.HIGH,
        verified_at="2026-08-25T00:00:00Z",
    )


def _portfolio_record(title: str, memory_type: MemoryType, **overrides) -> MemoryRecord:
    payload = {
        "status": MemoryStatus.VERIFIED,
        "confidence": MemoryConfidence.HIGH,
        "verified_at": "2026-08-25T00:00:00Z",
    }
    payload.update(overrides)
    return replace(
        MemoryDraft(
            type=memory_type,
            scope=MemoryScope.PORTFOLIO,
            project_id=None,
            title=title,
            body=f"{title} body",
        ).to_record(),
        **payload,
    )


def _write_pair(directory: Path, record: MemoryRecord) -> MemoryRecord:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{record.id}.md").write_text(f"# {record.title}\n", encoding="utf-8")
    (directory / f"{record.id}.json").write_text(
        json.dumps(record.to_json_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return record


class PortfolioMemoryTests(unittest.TestCase):
    def test_vault_is_plain_files_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NexusMemory"
            first = init_portfolio_vault(root)
            second = init_portfolio_vault(root)
            self.assertEqual(first, second)
            self.assertEqual(first, root)
            self.assertTrue((root / "HOME.md").exists())
            self.assertTrue((root / "VAULT_RULES.md").exists())
            self.assertTrue((root / "RETRIEVAL_PROTOCOL.md").exists())
            self.assertTrue((root / "projects").is_dir())
            for name in _VAULT_DIRS:
                self.assertTrue((root / name).is_dir(), name)
            self.assertTrue((root / ".nexus-memory" / "cache").is_dir())
            self.assertFalse((root / ".obsidian" / "plugins").exists())
            self.assertFalse((root / ".obsidian").exists())
            self.assertFalse((root / ".git").exists())

    def test_init_rejects_file_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "not-a-vault"
            target.write_text("nope\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                init_portfolio_vault(target)

    def test_templates_contain_required_statements(self):
        home = (_TEMPLATE_DIR / "HOME.md").read_text(encoding="utf-8")
        rules = (_TEMPLATE_DIR / "VAULT_RULES.md").read_text(encoding="utf-8")
        protocol = (_TEMPLATE_DIR / "RETRIEVAL_PROTOCOL.md").read_text(encoding="utf-8")
        for label in (
            "Projects",
            "Domains",
            "Patterns",
            "Lessons",
            "Decisions",
            "Incidents",
        ):
            self.assertIn(label, home)
        rules_lower = rules.lower()
        self.assertIn("repository/current evidence beats vault memory", rules_lower)
        self.assertIn("do not store secrets", rules_lower)
        self.assertIn("only verified memory is normal recall", rules_lower)
        self.assertIn("project facts remain project-scoped", rules_lower)
        self.assertIn(
            "bridge cards are pointers, not duplicated project wikis",
            rules_lower,
        )
        self.assertIn("derived indexes are disposable", rules_lower)
        self.assertIn("HOT → WARM → COLD", protocol)
        self.assertIn("progressive disclosure", protocol.lower())
        self.assertIn("stop retrieval once sufficient context exists", protocol.lower())

    def test_init_copies_templates_and_never_overwrites_user_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NexusMemory"
            init_portfolio_vault(root)
            expected_home = (_TEMPLATE_DIR / "HOME.md").read_text(encoding="utf-8")
            self.assertEqual(
                (root / "HOME.md").read_text(encoding="utf-8"), expected_home
            )
            (root / "HOME.md").write_text(
                "# User home\n\nDo not clobber this note.\n", encoding="utf-8"
            )
            extra = root / "projects" / "manual.md"
            extra.write_text("## Notes\n\nKeep me.\n", encoding="utf-8")
            init_portfolio_vault(root)
            self.assertEqual(
                (root / "HOME.md").read_text(encoding="utf-8"),
                "# User home\n\nDo not clobber this note.\n",
            )
            self.assertEqual(
                extra.read_text(encoding="utf-8"), "## Notes\n\nKeep me.\n"
            )

    def test_load_portfolio_memories_scope_order_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NexusMemory"
            init_portfolio_vault(root)
            late = _write_pair(
                root / "lessons",
                _portfolio_record("Zebra reusable lesson", MemoryType.LESSON),
            )
            early = _write_pair(
                root / "patterns",
                _portfolio_record("Alpha reusable pattern", MemoryType.PATTERN),
            )
            _write_pair(
                root / "decisions",
                replace(
                    _portfolio_record("Project fact leaked", MemoryType.DECISION),
                    scope=MemoryScope.PROJECT,
                    project_id="repo-1",
                ),
            )
            loaded = load_portfolio_memories(root)
            self.assertEqual([item.id for item in loaded], sorted((early.id, late.id)))
            self.assertTrue(all(item.scope == MemoryScope.PORTFOLIO for item in loaded))
            self.assertEqual({item.id for item in loaded}, {early.id, late.id})

            _write_pair(root / "incidents", late)
            with self.assertRaises(MemoryStoreError):
                load_portfolio_memories(root)

    def test_write_project_bridge_preserves_manual_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NexusMemory"
            init_portfolio_vault(root)
            first = ProjectBridge(
                project_id="repo-1",
                repository="github.com/example/repo-1",
                canonical_memory_path=".nexus/memory",
                status="active",
                current_focus="auth",
                related_memory_ids=("mem-pattern-alpha-aaaaaaaa",),
            )
            path = write_project_bridge(root, first)
            self.assertEqual(path, root / "projects" / "repo-1.md")
            existing = path.read_text(encoding="utf-8")
            path.write_text(
                existing.rstrip() + "\n\n## Notes\n\nHuman-owned note.\n",
                encoding="utf-8",
            )
            updated = ProjectBridge(
                project_id="repo-1",
                repository="github.com/example/repo-1",
                canonical_memory_path=".nexus/memory",
                status="paused",
                current_focus="billing",
                related_memory_ids=("mem-pattern-alpha-aaaaaaaa",),
            )
            write_project_bridge(root, updated)
            text = path.read_text(encoding="utf-8")
            self.assertIn("## Notes", text)
            self.assertIn("Human-owned note.", text)
            self.assertIn("Current focus: billing", text)
            self.assertNotIn("Current focus: auth", text)
            self.assertEqual(text.count("<!-- NEXUS:GENERATED:START -->"), 1)
            self.assertEqual(text.count("<!-- NEXUS:GENERATED:END -->"), 1)
            self.assertIn("Status: paused", text)

    def test_write_project_bridge_rejects_parent_traversal_without_changing_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NexusMemory"
            init_portfolio_vault(root)
            home = root / "HOME.md"
            original_home = home.read_text(encoding="utf-8")
            bridge = ProjectBridge(
                project_id="../HOME",
                repository="github.com/example/repo-1",
                canonical_memory_path=".nexus/memory",
            )

            with self.assertRaises(ValueError):
                write_project_bridge(root, bridge)

            self.assertEqual(home.read_text(encoding="utf-8"), original_home)

    def test_write_project_bridge_rejects_unsafe_project_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NexusMemory"
            init_portfolio_vault(root)
            for project_id in ("", "foo/bar", r"foo\bar"):
                with self.subTest(project_id=project_id):
                    bridge = ProjectBridge(
                        project_id=project_id,
                        repository="github.com/example/repo-1",
                        canonical_memory_path=".nexus/memory",
                    )
                    with self.assertRaises(ValueError):
                        write_project_bridge(root, bridge)

    def test_write_project_bridge_rejects_resolved_path_outside_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NexusMemory"
            init_portfolio_vault(root)
            home = root / "HOME.md"
            original_home = home.read_text(encoding="utf-8")
            (root / "projects" / "repo-1.md").symlink_to(home)
            bridge = ProjectBridge(
                project_id="repo-1",
                repository="github.com/example/repo-1",
                canonical_memory_path=".nexus/memory",
            )

            with self.assertRaises(ValueError):
                write_project_bridge(root, bridge)

            self.assertEqual(home.read_text(encoding="utf-8"), original_home)

    def test_search_memory_without_portfolio_is_project_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            cache_home = root / "cache"
            init_project_memory(project_root)
            included = write_memory(
                project_root, _verified_project("Retry idempotency")
            )
            hits = search_memory(
                project_root,
                "idempotency",
                MemoryQueryContext(project_id="repo-1"),
                portfolio_root=None,
                cache_home=cache_home,
            )
            self.assertGreaterEqual(len(hits), 1)
            self.assertEqual(hits[0].record.id, included.id)
            self.assertTrue(
                all(hit.record.scope == MemoryScope.PROJECT for hit in hits)
            )

    def test_search_memory_loads_portfolio_when_root_supplied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            vault = root / "NexusMemory"
            cache_home = root / "cache"
            init_project_memory(project_root)
            write_memory(project_root, _verified_project("Retry idempotency"))
            init_portfolio_vault(vault)
            portfolio = _write_pair(
                vault / "patterns",
                _portfolio_record(
                    "Webhook consumers require stable keys",
                    MemoryType.PATTERN,
                ),
            )
            hits = search_memory(
                project_root,
                "webhook consumers keys",
                MemoryQueryContext(project_id="repo-1"),
                portfolio_root=vault,
                cache_home=cache_home,
            )
            self.assertIn(portfolio.id, [hit.record.id for hit in hits])
            self.assertTrue(
                any(hit.record.scope == MemoryScope.PORTFOLIO for hit in hits)
            )
