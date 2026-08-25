import json
import tempfile
import unittest
from pathlib import Path

from nexus_harness.lockfile import write_lock
from nexus_harness.validate import validate_repository

CANONICAL_SKILLS = (
    "accessibility",
    "nexus-frontend",
    "nexus-handoff",
    "nexus-quality",
    "nexus-ship",
    "nexus-verify",
    "nexus-workflow",
)


def _minimal_repo(root: Path) -> Path:
    (root / "core" / "policies").mkdir(parents=True)
    (root / "core" / "constitution.md").write_text(
        "NEXUS WORKFLOW IS MANDATORY.\n",
        encoding="utf-8",
    )
    (root / "core" / "policies" / "production.toml").write_text(
        "[deploy]\nrequires_explicit_gate = true\n",
        encoding="utf-8",
    )
    (root / "profiles").mkdir()
    (root / "profiles" / "default.toml").write_text(
        '[profile]\nname = "default"\n',
        encoding="utf-8",
    )
    for name in CANONICAL_SKILLS:
        skill = root / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    example = root / "upstream" / "example"
    example.mkdir(parents=True)
    (example / "SKILL.md").write_text("upstream\n", encoding="utf-8")
    vendor = {
        "schema_version": 1,
        "sources": [
            {
                "id": "example",
                "kind": "export",
                "revision_kind": "content_sha256",
                "revision": "a" * 64,
                "canonical_path": "upstream/example",
            }
        ],
    }
    (root / "upstream" / "vendor-lock.json").write_text(
        json.dumps(vendor, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "dist").mkdir()
    (root / "dist" / ".gitkeep").write_bytes(b"")
    write_lock(root)
    return root


class ValidateTests(unittest.TestCase):
    def test_repository_has_no_appledouble_or_generated_drift(self):
        result = validate_repository(Path("."))
        self.assertEqual(result.errors, ())

    def test_appledouble_in_canonical_tree_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_repo(Path(tmp))
            (root / "core" / "._junk").write_text("meta", encoding="utf-8")
            result = validate_repository(root)
            self.assertTrue(result.errors)
            self.assertTrue(
                any("appledouble" in error.lower() for error in result.errors),
                msg=result.errors,
            )

    def test_constitution_model_names_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_repo(Path(tmp))
            (root / "core" / "constitution.md").write_text(
                "Use claude-sonnet for coding.\n",
                encoding="utf-8",
            )
            write_lock(root)
            result = validate_repository(root)
            self.assertTrue(result.errors)
            self.assertTrue(
                any("model" in error.lower() for error in result.errors),
                msg=result.errors,
            )

    def test_generated_hash_drift_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_repo(Path(tmp))
            (root / "dist" / "generated.txt").write_text(
                "changed",
                encoding="utf-8",
            )
            result = validate_repository(root)
            self.assertTrue(result.errors)
            self.assertTrue(
                any("drift" in error.lower() for error in result.errors),
                msg=result.errors,
            )

    def test_canonical_hash_drift_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_repo(Path(tmp))
            (root / "core" / "constitution.md").write_text(
                "NEXUS WORKFLOW IS MANDATORY.\nstale\n",
                encoding="utf-8",
            )
            result = validate_repository(root)
            self.assertTrue(result.errors)
            self.assertTrue(
                any(
                    "canonical" in error.lower() and "drift" in error.lower()
                    for error in result.errors
                ),
                msg=result.errors,
            )

    def test_adapter_version_drift_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_repo(Path(tmp))
            lock_path = root / "harness.lock"
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            payload["adapter_versions"]["claude"] = 99
            lock_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            result = validate_repository(root)
            self.assertTrue(result.errors)
            self.assertTrue(
                any(
                    "adapter" in error.lower() and "drift" in error.lower()
                    for error in result.errors
                ),
                msg=result.errors,
            )

    def test_lock_includes_profiles_in_canonical_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_repo(Path(tmp))
            payload = json.loads((root / "harness.lock").read_text(encoding="utf-8"))
            self.assertIn("profiles/default.toml", payload["canonical_hashes"])

    def test_ip_production_target_in_core_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_repo(Path(tmp))
            (root / "core" / "policies" / "production.toml").write_text(
                'host = "203.0.113.10"\n',
                encoding="utf-8",
            )
            write_lock(root)
            result = validate_repository(root)
            self.assertTrue(result.errors)
            self.assertTrue(
                any("production target" in error.lower() for error in result.errors),
                msg=result.errors,
            )

    def test_extra_skill_dir_fails_uniqueness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_repo(Path(tmp))
            extra = root / "skills" / "extra-skill"
            extra.mkdir()
            (extra / "SKILL.md").write_text("# extra\n", encoding="utf-8")
            write_lock(root)
            result = validate_repository(root)
            self.assertTrue(result.errors)
            self.assertTrue(
                any("canonical skills" in error.lower() for error in result.errors),
                msg=result.errors,
            )

    def test_appledouble_under_inputs_does_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_repo(Path(tmp))
            frozen = root / "inputs" / "copy"
            frozen.mkdir(parents=True)
            (frozen / "._junk").write_text("meta", encoding="utf-8")
            (root / "inputs" / "._also").write_text("meta", encoding="utf-8")
            result = validate_repository(root)
            self.assertEqual(result.errors, ())


if __name__ == "__main__":
    unittest.main()
