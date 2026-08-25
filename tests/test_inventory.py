import tempfile
import unittest
from pathlib import Path

from nexus_harness.inventory import scan_tree


class InventoryTests(unittest.TestCase):
    def test_scan_ignores_appledouble_and_counts_hash_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").write_text("same", encoding="utf-8")
            (root / "b").write_text("same", encoding="utf-8")
            (root / "._a").write_text("metadata", encoding="utf-8")

            report = scan_tree(root)

            self.assertEqual(report.file_count, 2)
            self.assertEqual(report.duplicate_file_count, 1)
            self.assertEqual(report.appledouble_count, 1)
