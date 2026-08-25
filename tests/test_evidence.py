import tempfile
import unittest
from pathlib import Path

from nexus_harness.evidence import Evidence, append_evidence, read_evidence


class EvidenceTests(unittest.TestCase):
    def test_evidence_is_stale_for_different_diff(self):
        item = Evidence("ev-1", "vitest", 0, "abc123", "tests pass")
        self.assertFalse(item.is_fresh("def456"))

    def test_evidence_is_fresh_for_matching_diff(self):
        item = Evidence("ev-1", "vitest", 0, "abc123", "tests pass")
        self.assertTrue(item.is_fresh("abc123"))

    def test_exit_code_is_stored_and_does_not_affect_freshness(self):
        item = Evidence("ev-2", "pytest", 1, "abc123", "tests failed")
        self.assertEqual(item.exit_code, 1)
        self.assertTrue(item.is_fresh("abc123"))
        self.assertFalse(item.is_fresh("other"))

    def test_jsonl_roundtrip(self):
        item = Evidence(
            "ev-1",
            "vitest",
            0,
            "abc123",
            "tests pass",
            artifact="artifacts/out.txt",
            limitation="no browser",
            timestamp="2026-08-25T12:00:00+00:00",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.jsonl"
            append_evidence(path, item)
            loaded = read_evidence(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "ev-1")
        self.assertEqual(loaded[0].command, "vitest")
        self.assertEqual(loaded[0].exit_code, 0)
        self.assertEqual(loaded[0].diff_hash, "abc123")
        self.assertEqual(loaded[0].summary, "tests pass")
        self.assertEqual(loaded[0].artifact, "artifacts/out.txt")
        self.assertEqual(loaded[0].limitation, "no browser")
        self.assertEqual(loaded[0].timestamp, "2026-08-25T12:00:00+00:00")
        self.assertTrue(loaded[0].is_fresh("abc123"))

    def test_append_only_keeps_two_records(self):
        first = Evidence("ev-1", "vitest", 0, "abc123", "unit pass")
        second = Evidence("ev-2", "playwright", 0, "abc123", "e2e pass")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.jsonl"
            append_evidence(path, first)
            append_evidence(path, second)
            loaded = read_evidence(path)

        self.assertEqual([item.id for item in loaded], ["ev-1", "ev-2"])
        self.assertEqual(loaded[0].command, "vitest")
        self.assertEqual(loaded[1].command, "playwright")
