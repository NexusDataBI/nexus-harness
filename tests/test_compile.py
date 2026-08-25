import json
import tempfile
import unittest
from pathlib import Path

from nexus_harness.adapters import render_all
from nexus_harness.lockfile import build_lock, serialize_lock


class CompileTests(unittest.TestCase):
    def test_second_render_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            first = render_all(root)
            second = render_all(root)

            self.assertEqual(first, second)

    def test_lock_json_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "core" / "constitution.md").write_bytes(b"canonical")
            (root / "skills" / "example").mkdir(parents=True)
            (root / "skills" / "example" / "SKILL.md").write_bytes(b"skill")
            (root / "upstream").mkdir()
            (root / "upstream" / "vendor-lock.json").write_bytes(b"{}")
            (root / "dist").mkdir()
            (root / "dist" / ".gitkeep").write_bytes(b"")
            (root / "dist" / "generated.txt").write_bytes(b"generated")

            first = serialize_lock(build_lock(root))
            second = serialize_lock(build_lock(root))

            self.assertEqual(first, second)
            self.assertEqual(json.loads(first), json.loads(second))

    def test_adapter_versions_include_all_runtimes(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = build_lock(Path(tmp))

        self.assertEqual(
            set(lock["adapter_versions"]),
            {"claude", "cursor", "codex"},
        )


if __name__ == "__main__":
    unittest.main()
