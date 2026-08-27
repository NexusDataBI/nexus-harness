import json
import tempfile
import unittest
from pathlib import Path

from nexus_harness.adapters import render_all
from nexus_harness.compile import compile_harness
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

    def test_compile_materializes_render_all_and_non_empty_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "core" / "constitution.md").write_text(
                "NEXUS WORKFLOW IS MANDATORY.\n", encoding="utf-8"
            )
            lock = compile_harness(root)
            hashes = lock["generated_hashes"]
            self.assertTrue(hashes)
            self.assertIn("dist/hooks/nexus_event.py", hashes)
            self.assertTrue((root / "dist" / "hooks" / "nexus_event.py").is_file())
            self.assertTrue(
                (root / "dist" / "src" / "nexus_harness" / "hooks.py").is_file()
            )

    def test_generated_hashes_exclude_engine_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "core" / "constitution.md").write_text(
                "NEXUS WORKFLOW IS MANDATORY.\n", encoding="utf-8"
            )
            lock = build_lock(root)
        generated = lock["generated_hashes"]
        engine = lock["engine_hashes"]
        self.assertTrue(generated)
        self.assertTrue(engine)
        self.assertTrue(any(path.startswith("dist/hooks/") for path in generated))
        self.assertFalse(
            any(path.startswith("dist/src/nexus_harness/") for path in generated)
        )
        self.assertTrue(
            any(path.startswith("dist/src/nexus_harness/") for path in engine)
        )

    def test_engine_byte_change_does_not_churn_generated_hashes(self):
        from nexus_harness.lockfile import (
            expected_engine_hashes,
            expected_generated_hashes,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "core" / "constitution.md").write_text("one\n", encoding="utf-8")
            generated = expected_generated_hashes(root)
            engine = expected_engine_hashes(root)
            (root / "core" / "constitution.md").write_text("two\n", encoding="utf-8")
            generated_after_core = expected_generated_hashes(root)
            engine_after_core = expected_engine_hashes(root)
        self.assertNotEqual(generated, generated_after_core)
        self.assertEqual(engine, engine_after_core)
        self.assertNotEqual(generated, engine)


if __name__ == "__main__":
    unittest.main()
