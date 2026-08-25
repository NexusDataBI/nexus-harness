import tempfile
import unittest
from pathlib import Path

from nexus_harness.inventory import scan_tree


class InventoryTests(unittest.TestCase):
    def test_scan_ignores_appledouble_and_counts_hash_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = "same"
            appledouble_content = "metadata"
            (root / "a").write_text(content, encoding="utf-8")
            (root / "b").write_text(content, encoding="utf-8")
            (root / "._a").write_text(appledouble_content, encoding="utf-8")

            report = scan_tree(root)
            file_bytes = len(content.encode("utf-8"))
            appledouble_bytes = len(appledouble_content.encode("utf-8"))

            self.assertEqual(report.file_count, 2)
            self.assertEqual(report.duplicate_file_count, 1)
            self.assertEqual(report.appledouble_count, 1)
            self.assertEqual(report.total_bytes, file_bytes * 2)
            self.assertEqual(report.redundant_bytes, file_bytes)
            self.assertNotEqual(
                report.total_bytes,
                file_bytes * 2 + appledouble_bytes,
            )
