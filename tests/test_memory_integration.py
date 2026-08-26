import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nexus_harness.memory import (
    build_context_capsule,
    checkpoint_memory_candidates,
    collect_memory_candidates,
    compute_memory_freshness,
    consolidate_memory,
    init_portfolio_vault,
    load_project_memories,
    memory_doctor,
    restore_memory_candidates,
    search_memory,
    session_recall,
    supersede_memory,
    verify_memory,
    write_memory,
)
from nexus_harness.memory.capsule import load_capsule_policy
from nexus_harness.memory.cli import main as memory_cli_main
from nexus_harness.memory.freshness import (
    AuthorityContradiction,
    FreshnessStatus,
    TruthStrength,
)
from nexus_harness.memory.guard import MemoryGuardError
from nexus_harness.memory.lifecycle import CandidateSignal
from nexus_harness.memory.models import (
    MemoryDraft,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.retrieval import MemoryQueryContext, default_index_path
from nexus_harness.memory.store import init_project_memory, read_memory


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_repo(root: Path) -> None:
    _run_git(root, "init", "-b", "main")
    _run_git(root, "config", "user.name", "Nexus Test")
    _run_git(root, "config", "user.email", "nexus-test@example.com")
    _run_git(root, "config", "commit.gpgsign", "false")


def _commit_file(root: Path, relative: str, content: str, message: str) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _run_git(root, "add", "--", relative)
    _run_git(root, "commit", "-m", message)
    return _run_git(root, "rev-parse", "HEAD")


def _invariant_draft(**overrides) -> MemoryDraft:
    payload = {
        "type": MemoryType.INVARIANT,
        "scope": MemoryScope.PROJECT,
        "project_id": "repo-1",
        "title": "Auth sessions stay isolated",
        "body": "Auth session cookies must stay isolated per tenant.",
        "sources": (MemorySource("approved_spec", "SPEC-AUTH"),),
        "related_paths": ("src/auth/**",),
        "tags": ("auth", "session"),
    }
    payload.update(overrides)
    return MemoryDraft(**payload)


class MemoryIntegrationProofTests(unittest.TestCase):
    def test_current_repo_truth_wins_over_verified_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            cache_home = Path(tmp) / "cache"
            root.mkdir()
            _init_repo(root)
            commit = _commit_file(
                root,
                "src/auth/session.py",
                "def load_session():\n    return 'repo truth'\n",
                "repo truth",
            )
            init_project_memory(root)
            record = write_memory(root, _invariant_draft().to_record())
            verify_memory(root, record.id, current_commit=commit)

            capsule = session_recall(
                root,
                project_id="repo-1",
                query="auth session",
                affected_paths=("src/auth/session.py",),
                cache_home=cache_home,
                contradictions=(
                    AuthorityContradiction(
                        memory_id=record.id,
                        authority=TruthStrength.CURRENT_REPO,
                        pointer="src/auth/session.py",
                    ),
                ),
            )

            self.assertNotIn(record.id, capsule.hot)
            self.assertNotIn(record.id, capsule.warm)
            self.assertIn(record.id, capsule.warnings)
            self.assertIn("CURRENT_REPO", capsule.warnings)
            self.assertIn("src/auth/session.py", capsule.warnings)

    def test_plan25_end_to_end_scenario_without_portfolio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            cache_home = Path(tmp) / "cache"
            root.mkdir()
            _init_repo(root)
            commit_a = _commit_file(
                root,
                "src/auth/session.py",
                "def load_session():\n    return 'A'\n",
                "A",
            )

            # 2. initialize project memory
            memory_root = init_project_memory(root)
            self.assertTrue(memory_root.is_dir())

            # 3. CANDIDATE invariant with approved source and src/auth/**
            record = write_memory(root, _invariant_draft().to_record())
            self.assertEqual(record.status, MemoryStatus.CANDIDATE)

            # 4. candidate search does not auto-return it for normal recall
            candidate_hits = search_memory(
                root,
                "auth session",
                MemoryQueryContext(
                    project_id="repo-1",
                    affected_paths=("src/auth/session.py",),
                ),
                cache_home=cache_home,
            )
            self.assertEqual(candidate_hits, [])

            # 5. verify it at commit A
            verified = verify_memory(root, record.id, current_commit=commit_a)
            self.assertEqual(verified.status, MemoryStatus.VERIFIED)
            self.assertEqual(verified.valid_at_commit, commit_a)

            # 6. search auth session with affected path — top hit
            hits = search_memory(
                root,
                "auth session",
                MemoryQueryContext(
                    project_id="repo-1",
                    affected_paths=("src/auth/session.py",),
                ),
                cache_home=cache_home,
            )
            self.assertGreaterEqual(len(hits), 1)
            self.assertEqual(hits[0].record.id, record.id)

            # 7. capsule includes memory ID and provenance
            capsule = build_context_capsule(
                project_id="repo-1",
                diff_hash=commit_a,
                hits=hits,
                hot_memory_ids=(record.id,),
                policy=load_capsule_policy(),
            )
            self.assertIn(record.id, capsule.text)
            self.assertIn(record.id, capsule.hot)
            self.assertIn("source:", capsule.hot)

            # 8. modify/commit src/auth/session.py as commit B
            _commit_file(
                root,
                "src/auth/session.py",
                "def load_session():\n    return 'B'\n",
                "B",
            )

            # 9. freshness is STALE
            freshness = compute_memory_freshness(root, read_memory(root, record.id))
            self.assertEqual(freshness.status, FreshnessStatus.STALE)

            # 10. public session_recall leaves HOT/WARM and only warns
            stale_capsule = session_recall(
                root,
                project_id="repo-1",
                query="auth session",
                affected_paths=("src/auth/session.py",),
                cache_home=cache_home,
            )
            self.assertNotIn(record.id, stale_capsule.hot)
            self.assertNotIn(record.id, stale_capsule.warm)
            warned = record.id in stale_capsule.warnings or (
                "STALE/CONFLICT WARNINGS" in stale_capsule.text
                and record.id in stale_capsule.text
            )
            self.assertTrue(warned, "stale memory must appear in capsule warnings")

            # 11. delete derived SQLite index — search still works through fallback
            db_path = default_index_path("repo-1", cache_home=cache_home)
            if db_path.exists():
                db_path.unlink()
            self.assertFalse(db_path.exists())
            with patch(
                "nexus_harness.memory.retrieval.fts5_available", return_value=False
            ):
                fallback_hits = search_memory(
                    root,
                    "auth session",
                    MemoryQueryContext(
                        project_id="repo-1",
                        affected_paths=("src/auth/session.py",),
                        include_stale=True,
                    ),
                    cache_home=cache_home,
                )
            self.assertGreaterEqual(len(fallback_hits), 1)
            self.assertEqual(fallback_hits[0].record.id, record.id)

            # 12. secret-like draft is rejected
            secret = "ghp_abcdefghijklmnopqrstuvwxyz01"
            with self.assertRaises(MemoryGuardError) as ctx:
                write_memory(
                    root,
                    _invariant_draft(
                        title="Leaked credential",
                        body=f"do not store {secret}",
                    ).to_record(),
                )
            self.assertNotIn(secret, str(ctx.exception))

            # 13. no portfolio vault — project memory stays valid; stale VERIFIED is a doctor finding
            loaded = load_project_memories(root)
            self.assertEqual([item.id for item in loaded], [record.id])
            report = memory_doctor(root)
            self.assertEqual(report.portfolio_records, 0)
            self.assertIn(
                "stale_status_inconsistent",
                [finding.code for finding in report.findings],
            )
            self.assertEqual(report.gate, "FAIL")


class MemorySessionFacadeTests(unittest.TestCase):
    def test_session_recall_returns_capsule_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            cache_home = Path(tmp) / "cache"
            root.mkdir()
            _init_repo(root)
            commit = _commit_file(
                root,
                "src/auth/session.py",
                "def load_session():\n    return 'A'\n",
                "A",
            )
            init_project_memory(root)
            record = write_memory(root, _invariant_draft().to_record())
            verify_memory(root, record.id, current_commit=commit)
            before = {
                path: path.read_bytes()
                for path in (root / ".nexus" / "memory").rglob("*")
                if path.is_file()
            }

            with patch(
                "nexus_harness.memory.retrieval.default_index_path",
                side_effect=lambda repo_id, cache_home=None: default_index_path(
                    repo_id, cache_home=cache_home or Path(tmp) / "cache"
                ),
            ):
                capsule = session_recall(
                    root,
                    project_id="repo-1",
                    query="auth session",
                    affected_paths=("src/auth/session.py",),
                )

            after = {
                path: path.read_bytes()
                for path in (root / ".nexus" / "memory").rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertIn(record.id, capsule.text)

    def test_checkpoint_restore_roundtrip_and_missing_path(self):
        drafts = collect_memory_candidates(
            project_id="repo-1",
            task_id="task-1",
            signals=(
                CandidateSignal(
                    kind="invariant",
                    title="Auth sessions stay isolated",
                    statement="Auth session cookies must stay isolated per tenant.",
                    sources=(MemorySource("approved_spec", "SPEC-AUTH"),),
                    related_paths=("src/auth/**",),
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scratch" / "candidates.json"
            written = checkpoint_memory_candidates(path, drafts)
            self.assertEqual(written, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(payload, list)
            self.assertNotIn("transcript", path.read_text(encoding="utf-8"))
            restored = restore_memory_candidates(path)
            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0].title, drafts[0].title)
            self.assertEqual(restore_memory_candidates(Path(tmp) / "missing.json"), [])

    def test_consolidate_leaves_insufficient_sources_as_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            weak = MemoryDraft(
                type=MemoryType.DECISION,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Guessed queue",
                body="An unsupported guess about the queue.",
            )
            strong = MemoryDraft(
                type=MemoryType.DECISION,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Use queue X",
                body="Queue X is the selected transport.",
                sources=(MemorySource("adr", "ADR-001"),),
            )
            results = consolidate_memory(
                root,
                [weak, strong],
                current_commit="abc123",
            )
            self.assertEqual(len(results), 2)
            by_title = {item.title: item for item in results}
            self.assertEqual(by_title[weak.title].status, MemoryStatus.CANDIDATE)
            self.assertEqual(by_title[strong.title].status, MemoryStatus.VERIFIED)
            self.assertEqual(by_title[strong.title].valid_at_commit, "abc123")


class MemoryPublicApiAndCliTests(unittest.TestCase):
    def test_public_api_exports_plan3_contract(self):
        import nexus_harness.memory as memory

        for name in (
            "load_project_memories",
            "write_memory",
            "verify_memory",
            "supersede_memory",
            "compute_memory_freshness",
            "search_memory",
            "build_context_capsule",
            "collect_memory_candidates",
            "init_portfolio_vault",
            "memory_doctor",
            "session_recall",
            "checkpoint_memory_candidates",
            "restore_memory_candidates",
            "consolidate_memory",
        ):
            self.assertTrue(callable(getattr(memory, name)), name)

    def test_cli_supports_local_subcommands_and_rejects_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = Path.cwd()
            os.chdir(root)
            try:
                self.assertEqual(memory_cli_main(["init-project"]), 0)
                self.assertEqual(memory_cli_main(["status"]), 0)
                self.assertEqual(memory_cli_main(["doctor"]), 0)
                self.assertEqual(memory_cli_main(["candidates"]), 0)
                self.assertNotEqual(memory_cli_main(["push"]), 0)
                self.assertNotEqual(memory_cli_main(["sync"]), 0)
                self.assertNotEqual(memory_cli_main(["remote"]), 0)
            finally:
                os.chdir(previous)

    def test_cli_init_vault_is_local_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            self.assertEqual(memory_cli_main(["init-vault", str(vault)]), 0)
            self.assertTrue((vault / "HOME.md").is_file())
            self.assertEqual(init_portfolio_vault(vault), vault)
            self.assertTrue(callable(supersede_memory))
