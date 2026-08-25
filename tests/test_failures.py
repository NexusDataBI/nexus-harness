import unittest

from nexus_harness.failures import FailureMemory


class FailureTests(unittest.TestCase):
    def test_second_identical_failure_requests_diagnosis(self):
        memory = FailureMemory()
        first = memory.record("vitest", 1, "AssertionError: expected 1 got 0")
        result = memory.record("vitest", 1, "AssertionError: expected 1 got 0")
        self.assertEqual(first.action, "retry")
        self.assertEqual(result.action, "diagnose")

    def test_timestamp_and_volatile_ids_share_fingerprint(self):
        memory = FailureMemory()
        first = memory.record(
            "pytest",
            1,
            "AssertionError at 2026-08-25T16:42:00Z pid=12345 in /tmp/pytest-of-user/test_a.py",
        )
        second = memory.record(
            "pytest",
            1,
            "AssertionError at 2026-08-25T17:01:33Z pid=99999 in /tmp/pytest-of-ci/test_a.py",
        )
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(second.action, "diagnose")

    def test_ceiling_without_progress_blocks(self):
        memory = FailureMemory()
        first = memory.record("vitest", 1, "AssertionError: expected 1 got 0")
        second = memory.record("vitest", 1, "AssertionError: expected 1 got 0")
        third = memory.record("vitest", 1, "AssertionError: expected 1 got 0")
        self.assertEqual(first.action, "retry")
        self.assertEqual(second.action, "diagnose")
        self.assertEqual(third.action, "blocked")

    def test_material_diff_hash_change_resets_progress(self):
        memory = FailureMemory()
        memory.record("vitest", 1, "AssertionError: expected 1 got 0", diff_hash="aaa")
        memory.record("vitest", 1, "AssertionError: expected 1 got 0", diff_hash="aaa")
        progressed = memory.record(
            "vitest", 1, "AssertionError: expected 1 got 0", diff_hash="bbb"
        )
        self.assertEqual(progressed.action, "retry")
        diagnosed = memory.record(
            "vitest", 1, "AssertionError: expected 1 got 0", diff_hash="bbb"
        )
        blocked = memory.record(
            "vitest", 1, "AssertionError: expected 1 got 0", diff_hash="bbb"
        )
        self.assertEqual(diagnosed.action, "diagnose")
        self.assertEqual(blocked.action, "blocked")
