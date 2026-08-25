import unittest
from dataclasses import replace

from nexus_harness.memory.freshness import (
    FreshnessStatus,
    TruthStrength,
    compute_memory_freshness,
    resolve_contradiction,
)
from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryRecord,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
    MemoryType,
)
from tests.memory_git_helper import make_repo_with_changed_file


class MemoryFreshnessTests(unittest.TestCase):
    def record(self, commit, **overrides):
        payload = dict(
            schema_version=1,
            id="mem-component-auth-a1b2c3d4",
            type=MemoryType.COMPONENT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Auth entrypoint",
            body="Auth lives in src/auth.py",
            status=MemoryStatus.VERIFIED,
            confidence=MemoryConfidence.HIGH,
            created_at="2026-08-25T00:00:00Z",
            verified_at="2026-08-25T00:00:00Z",
            valid_at_commit=commit,
            sources=(),
            evidence_ids=(),
            related_paths=("src/auth.py",),
            tags=("auth",),
            supersedes=(),
            sensitivity=MemorySensitivity.INTERNAL,
        )
        payload.update(overrides)
        return MemoryRecord(**payload)

    def test_changed_related_path_is_stale(self):
        # Test helper creates a temporary git repository with commit A,
        # modifies src/auth.py, commits B and evaluates record valid at A.
        root, base_commit = make_repo_with_changed_file("src/auth.py")
        result = compute_memory_freshness(root, self.record(base_commit))
        self.assertEqual(result.status, FreshnessStatus.STALE)
        self.assertIn("src/auth.py", result.changed_paths)

    def test_unrelated_path_change_is_fresh(self):
        root, base_commit = make_repo_with_changed_file("src/other.py")
        result = compute_memory_freshness(root, self.record(base_commit))
        self.assertEqual(result.status, FreshnessStatus.FRESH)
        self.assertEqual(result.changed_paths, ())

    def test_glob_prefix_related_path_is_stale(self):
        root, base_commit = make_repo_with_changed_file("src/auth/session.py")
        result = compute_memory_freshness(
            root,
            self.record(base_commit, related_paths=("src/auth/**",)),
        )
        self.assertEqual(result.status, FreshnessStatus.STALE)
        self.assertIn("src/auth/session.py", result.changed_paths)

    def test_non_verified_memory_is_unknown(self):
        root, base_commit = make_repo_with_changed_file("src/auth.py")
        record = replace(self.record(base_commit), status=MemoryStatus.CANDIDATE)
        result = compute_memory_freshness(root, record)
        self.assertEqual(result.status, FreshnessStatus.UNKNOWN)
        self.assertIn("status_not_verified", result.reasons)

    def test_missing_valid_at_commit_is_unknown(self):
        root, _ = make_repo_with_changed_file("src/auth.py")
        result = compute_memory_freshness(root, self.record(None))
        self.assertEqual(result.status, FreshnessStatus.UNKNOWN)

    def test_no_related_paths_is_unknown(self):
        root, base_commit = make_repo_with_changed_file("src/auth.py")
        result = compute_memory_freshness(
            root,
            self.record(base_commit, related_paths=()),
        )
        self.assertEqual(result.status, FreshnessStatus.UNKNOWN)

    def test_unknown_commit_is_unknown(self):
        root, _ = make_repo_with_changed_file("src/auth.py")
        result = compute_memory_freshness(root, self.record("0" * 40))
        self.assertEqual(result.status, FreshnessStatus.UNKNOWN)


class ContradictionResolutionTests(unittest.TestCase):
    def test_truth_strength_values_are_exact(self):
        self.assertEqual(TruthStrength.CURRENT_INSTRUCTION, 900)
        self.assertEqual(TruthStrength.HARD_POLICY, 850)
        self.assertEqual(TruthStrength.FRESH_EXECUTABLE_EVIDENCE, 800)
        self.assertEqual(TruthStrength.CURRENT_REPO, 750)
        self.assertEqual(TruthStrength.CANONICAL_DOC, 700)
        self.assertEqual(TruthStrength.WORK_RECORD, 650)
        self.assertEqual(TruthStrength.VERIFIED_PROJECT_MEMORY, 500)
        self.assertEqual(TruthStrength.VERIFIED_PORTFOLIO_MEMORY, 450)
        self.assertEqual(TruthStrength.STALE_MEMORY, 100)
        self.assertEqual(TruthStrength.SESSION_RECOLLECTION, 50)

    def test_current_repo_beats_verified_project_memory(self):
        result = resolve_contradiction(
            [
                ("memory-auth", TruthStrength.VERIFIED_PROJECT_MEMORY),
                ("repo-auth", TruthStrength.CURRENT_REPO),
            ]
        )
        self.assertEqual(result.winner, "repo-auth")
        self.assertFalse(result.requires_adjudication)
        self.assertIn("memory-auth", result.excluded)

    def test_equal_strength_memories_require_adjudication(self):
        result = resolve_contradiction(
            [
                ("mem-a", TruthStrength.VERIFIED_PROJECT_MEMORY),
                ("mem-b", TruthStrength.VERIFIED_PROJECT_MEMORY),
            ]
        )
        self.assertIsNone(result.winner)
        self.assertTrue(result.requires_adjudication)

    def test_stale_never_beats_verified(self):
        result = resolve_contradiction(
            [
                ("stale-auth", TruthStrength.STALE_MEMORY),
                ("verified-auth", TruthStrength.VERIFIED_PROJECT_MEMORY),
            ]
        )
        self.assertEqual(result.winner, "verified-auth")
        self.assertFalse(result.requires_adjudication)
        self.assertIn("stale-auth", result.excluded)
        self.assertGreater(
            TruthStrength.VERIFIED_PROJECT_MEMORY,
            TruthStrength.STALE_MEMORY,
        )
