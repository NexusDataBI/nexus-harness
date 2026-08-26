import unittest
from pathlib import Path

from nexus_harness.adapters import render_all


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = ROOT / "tests" / "golden"
_SKIP_NAMES = {".DS_Store"}
_SKIP_SUFFIXES = {".pyc", ".pyo"}


def _is_reviewed_golden(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name in _SKIP_NAMES or path.suffix in _SKIP_SUFFIXES:
        return False
    if "__pycache__" in path.parts:
        return False
    return True


class GoldenAdapterTests(unittest.TestCase):
    def test_rendered_files_match_reviewed_snapshots_byte_for_byte(self):
        rendered = {item.relative_path: item.content for item in render_all(ROOT)}
        expected = {
            path.relative_to(GOLDEN_ROOT).as_posix(): path.read_bytes()
            for path in GOLDEN_ROOT.rglob("*")
            if _is_reviewed_golden(path)
        }
        self.assertEqual(
            set(rendered),
            set(expected),
            "generated file set differs from reviewed goldens",
        )
        for relative_path in sorted(expected):
            self.assertEqual(
                rendered[relative_path],
                expected[relative_path],
                relative_path,
            )


if __name__ == "__main__":
    unittest.main()
