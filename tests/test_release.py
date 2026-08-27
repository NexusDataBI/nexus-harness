"""Reproducible v4 release builder. Preconditions are injected — never unittest discover."""

from __future__ import annotations

import json
import os
import tarfile
import tempfile
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from nexus_harness.release import (
    RELEASE_CHANNEL,
    RELEASE_SCHEMA,
    RELEASE_VERSION,
    CheckResult,
    ReleaseChecks,
    ReleaseError,
    build_release,
    logical_manifest,
)

HEX64 = "a" * 64


def setUpModule():
    os.environ["_NEXUS_RELEASE_UNITTEST_ACTIVE"] = "1"


def tearDownModule():
    os.environ.pop("_NEXUS_RELEASE_UNITTEST_ACTIVE", None)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _pass(name: str) -> object:
    return lambda root: CheckResult(name, True, f"injected {name}")


def _fail(name: str, message: str = "injected failure") -> object:
    return lambda root: CheckResult(name, False, message)


PASSING = ReleaseChecks(
    validate=_pass("validate"),
    tests=_pass("tests"),
    evals=_pass("evals"),
    golden=_pass("golden"),
    drift=_pass("drift"),
    acceptance=_pass("acceptance"),
    debt=_pass("debt"),
    migration=_pass("migration"),
    upstream=_pass("upstream"),
    secrets=_pass("secrets"),
)


def _fixture(root: Path) -> Path:
    _write(root / "core" / "constitution.md", "NEXUS WORKFLOW IS MANDATORY.\n")
    _write(root / "core" / "policies" / "production.toml", "[deploy]\n")
    _write(root / "skills" / "nexus-workflow" / "SKILL.md", "# workflow\n")
    _write(root / "scripts" / "validate", "#!/bin/sh\necho ok\n")
    _write(root / "docs" / "migration" / "final-report.md", "# migration\n")
    _write(root / "docs" / "release" / "v4-acceptance.md", "# acceptance\n")
    _write(
        root / "docs" / "migration" / "debt.json",
        json.dumps(
            {
                "schema_version": 1,
                "items": [
                    {
                        "id": "P8-X01",
                        "status": "resolved",
                        "target_plan": "plan-8",
                    }
                ],
            }
        )
        + "\n",
    )
    _write(
        root / "docs" / "migration" / "unique-heuristics.md",
        "| Source | Relationship | Status |\n"
        "| --- | --- | --- |\n"
        "| napkin | divergent | DISCARDED_WITH_REASON: note |\n",
    )
    _write(
        root / "docs" / "migration" / "skill-ledger.json",
        json.dumps(
            [
                {
                    "name": "napkin",
                    "relationship": "divergent",
                    "decision": "DISCARDED_WITH_REASON",
                    "target": "none",
                }
            ]
        )
        + "\n",
    )
    _write(root / "upstream" / "example" / "SKILL.md", "upstream\n")
    _write(
        root / "upstream" / "vendor-lock.json",
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "example",
                        "kind": "export",
                        "revision_kind": "content_sha256",
                        "revision": HEX64,
                        "canonical_path": "upstream/example",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
    )
    _write(root / "dist" / "generated.txt", "adapter-bytes\n")
    _write(root / "harness.lock", json.dumps({"schema_version": 1}) + "\n")
    _write(root / "README.md", "# Nexus Harness\n")
    _write(root / "evals" / "cases" / "backend-bug.json", "{}\n")
    return root


def _pollute(root: Path) -> None:
    _write(root / ".git" / "config", "[core]\n")
    _write(root / ".worktrees" / "other" / "file.txt", "nope\n")
    _write(root / ".superpowers" / "sdd" / "task-5-brief.md", "transient\n")
    _write(root / ".nexus" / "tasks" / "state.json", "{}\n")
    _write(root / "__pycache__" / "mod.cpython-314.pyc", "cache")
    _write(root / "core" / "__pycache__" / "x.pyc", "cache")
    _write(root / "core" / ".DS_Store", "apple")
    _write(root / "core" / "._appledouble", "meta")
    _write(root / "legacy" / "v3-export" / "old.md", "legacy\n")
    _write(root / "inputs" / "nexus-harness-export.tar.gz", "archive")
    _write(root / "screenshots" / "desktop.png", "png")
    _write(root / "traces" / "trace.zip", "trace")
    _write(root / ".env", "POSTHOG_PERSONAL_API_KEY=phx_secret\n")
    _write(root / "secrets" / "github.token", "ghp_secret\n")
    _write(root / "client-data" / "acelera.json", "{}\n")


class ReleaseManifestTests(unittest.TestCase):
    def test_release_manifest_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            first = build_release(
                root,
                checks=PASSING,
                source_commit="deadbeef",
                compile_adapters=False,
            )
            second = build_release(
                root,
                checks=PASSING,
                source_commit="deadbeef",
                compile_adapters=False,
            )
            self.assertEqual(logical_manifest(first), logical_manifest(second))
            self.assertEqual(first["schema"], RELEASE_SCHEMA)
            self.assertEqual(first["schema"], "nexus-harness-release/v1")
            self.assertEqual(first["version"], RELEASE_VERSION)
            self.assertEqual(first["version"], "4.0.0-rc1")
            self.assertEqual(first["channel"], RELEASE_CHANNEL)
            self.assertEqual(first["commit"], "deadbeef")
            self.assertTrue(first["lock_identity"])
            files = first["files"]
            self.assertEqual(files, sorted(files, key=lambda item: item["path"]))
            for item in files:
                self.assertIn("path", item)
                self.assertIn("sha256", item)
                self.assertIn("size", item)
                self.assertEqual(len(item["sha256"]), 64)


class ReleaseAssemblyTests(unittest.TestCase):
    def test_bundle_contains_canonical_trees_and_excludes_junk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            _pollute(root)
            manifest = build_release(
                root,
                checks=PASSING,
                source_commit="cafebabe",
                compile_adapters=False,
            )
            bundle = root / "release" / "nexus-harness-v4"
            self.assertTrue((bundle / "core" / "constitution.md").is_file())
            self.assertTrue((bundle / "dist" / "generated.txt").is_file())
            self.assertTrue((bundle / "scripts" / "validate").is_file())
            self.assertTrue(
                (bundle / "docs" / "migration" / "final-report.md").is_file()
            )
            self.assertTrue(
                (bundle / "docs" / "release" / "v4-acceptance.md").is_file()
            )
            self.assertTrue((bundle / "harness.lock").is_file())
            self.assertTrue((bundle / "INSTALL.md").is_file())
            install = (bundle / "INSTALL.md").read_text(encoding="utf-8")
            self.assertIn("4.0.0-rc1", install)
            self.assertIn("LOCAL RELEASE CANDIDATE", install)
            paths = {item["path"] for item in manifest["files"]}
            blob = "\n".join(sorted(paths))
            self.assertIn("nexus-harness-v4/core/constitution.md", paths)
            self.assertNotIn(".git", blob)
            self.assertNotIn(".worktrees", blob)
            self.assertNotIn(".superpowers", blob)
            self.assertNotIn(".nexus", blob)
            self.assertNotIn("__pycache__", blob)
            self.assertNotIn(".DS_Store", blob)
            self.assertNotIn("._appledouble", blob)
            self.assertNotIn("legacy/", blob)
            self.assertNotIn("inputs/", blob)
            self.assertNotIn("screenshots/", blob)
            self.assertNotIn("traces/", blob)
            self.assertNotIn(".env", blob)
            self.assertNotIn("github.token", blob)
            self.assertNotIn("client-data", blob)
            self.assertNotIn("phx_secret", blob)

    def test_archive_extracted_hashes_match_logical_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            manifest = build_release(
                root,
                checks=PASSING,
                source_commit="abcdef",
                compile_adapters=False,
            )
            archive = root / "release" / "nexus-harness-v4.tar.gz"
            self.assertTrue(archive.is_file())
            expected = {item["path"]: item for item in manifest["files"]}
            with tarfile.open(archive, "r:gz") as tar:
                members = [item for item in tar.getmembers() if item.isfile()]
                names = sorted(item.name for item in members)
                self.assertEqual(names, sorted(expected))
                for member in members:
                    extracted = tar.extractfile(member)
                    assert extracted is not None
                    data = extracted.read()
                    item = expected[member.name]
                    self.assertEqual(sha256(data).hexdigest(), item["sha256"])
                    self.assertEqual(len(data), item["size"])

    def test_skips_compile_when_dist_already_materialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            with patch("nexus_harness.release.compile_harness") as compile_fn:
                build_release(
                    root,
                    checks=PASSING,
                    source_commit="1",
                    compile_adapters=False,
                )
            compile_fn.assert_not_called()


class ReleasePreconditionTests(unittest.TestCase):
    def _refuse(self, **overrides):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            checks = replace(PASSING, **overrides)
            with self.assertRaises(ReleaseError) as ctx:
                build_release(
                    root,
                    checks=checks,
                    source_commit="1",
                    compile_adapters=False,
                )
            return str(ctx.exception)

    def test_refuses_when_validate_fails(self):
        message = self._refuse(validate=_fail("validate", "validate failed"))
        self.assertIn("validate", message.lower())

    def test_refuses_when_tests_fail(self):
        message = self._refuse(tests=_fail("tests", "tests failed"))
        self.assertIn("tests", message.lower())

    def test_refuses_when_evals_fail(self):
        message = self._refuse(evals=_fail("evals", "evals failed"))
        self.assertIn("evals", message.lower())

    def test_refuses_when_golden_fails(self):
        message = self._refuse(golden=_fail("golden", "golden failed"))
        self.assertIn("golden", message.lower())

    def test_refuses_when_drift_fails(self):
        message = self._refuse(drift=_fail("drift", "generated drift"))
        self.assertIn("drift", message.lower())

    def test_refuses_unresolved_plan8_debt(self):
        message = self._refuse(debt=_fail("debt", "unresolved Plan 8 debt: P8-X99"))
        self.assertIn("debt", message.lower())

    def test_refuses_unresolved_migration_decision(self):
        message = self._refuse(
            migration=_fail("migration", "unresolved migration decision")
        )
        self.assertIn("migration", message.lower())

    def test_refuses_invalid_upstream_lock(self):
        message = self._refuse(
            upstream=_fail("upstream", "upstream lock revision is not a hash")
        )
        self.assertIn("upstream", message.lower())

    def test_refuses_when_secret_scan_fails(self):
        message = self._refuse(secrets=_fail("secrets", "secret scan failed"))
        self.assertIn("secret", message.lower())

    def test_refuses_incomplete_acceptance_when_matrix_present(self):
        message = self._refuse(acceptance=_fail("acceptance", "acceptance incomplete"))
        self.assertIn("acceptance", message.lower())

    def test_does_not_refuse_for_unactivated_saas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            manifest = build_release(
                root,
                checks=PASSING,
                source_commit="1",
                compile_adapters=False,
            )
            self.assertEqual(manifest["version"], "4.0.0-rc1")

    def test_injected_preconditions_do_not_recurse_unittest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            with patch("subprocess.run") as run:
                build_release(
                    root,
                    checks=PASSING,
                    source_commit="1",
                    compile_adapters=False,
                )
            for call in run.call_args_list:
                argv = [str(part) for part in call.args[0]]
                self.assertNotIn("unittest", argv)
                self.assertNotIn("discover", argv)

    def test_default_tests_hook_refuses_to_recurse_from_unittest(self):
        from nexus_harness.release import default_check_tests

        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            with self.assertRaises(ReleaseError) as ctx:
                default_check_tests(root)
            self.assertIn("unittest", str(ctx.exception).lower())

    def test_default_upstream_rejects_missing_or_invalid_revision(self):
        from nexus_harness.release import default_check_upstream

        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            payload = json.loads(
                (root / "upstream" / "vendor-lock.json").read_text(encoding="utf-8")
            )
            payload["sources"][0]["revision"] = "not-a-hash"
            _write(
                root / "upstream" / "vendor-lock.json",
                json.dumps(payload) + "\n",
            )
            result = default_check_upstream(root)
            self.assertFalse(result.ok)
            missing = Path(tmp) / "missing"
            (missing / "upstream").mkdir(parents=True)
            result = default_check_upstream(missing)
            self.assertFalse(result.ok)

    def test_default_debt_rejects_unresolved_plan8_items(self):
        from nexus_harness.release import default_check_debt

        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            _write(
                root / "docs" / "migration" / "debt.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "items": [
                            {
                                "id": "P8-OPEN",
                                "status": "deferred",
                                "target_plan": "plan-8",
                            }
                        ],
                    }
                )
                + "\n",
            )
            result = default_check_debt(root)
            self.assertFalse(result.ok)
            self.assertIn("P8-OPEN", result.message)

    def test_default_check_secrets_skips_test_fixtures_and_placeholders(self):
        from nexus_harness.release import default_check_secrets

        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture(Path(tmp) / "repo")
            _write(
                root / "tests" / "test_posthog_config.py",
                'SECRET = "phx_supersecret_PERSONAL_KEY_do_not_leak"\n',
            )
            _write(
                root / "docs" / "operations" / "activation.md",
                "export POSTHOG_PERSONAL_API_KEY=$POSTHOG_PERSONAL_API_KEY\n",
            )
            result = default_check_secrets(root)
            self.assertTrue(result.ok, result.message)
            _write(root / "src" / "leaked.py", 'token = "phx_' + ("a" * 24) + '"\n')
            result = default_check_secrets(root)
            self.assertFalse(result.ok)
            self.assertIn("src/leaked.py", result.message)
            (root / "src" / "leaked.py").unlink()
            _write(
                root / "src" / "key.pem",
                "-----BEGIN OPENSSH PRIVATE KEY-----\n" + ("AAAA" * 16) + "\n",
            )
            result = default_check_secrets(root)
            self.assertFalse(result.ok)
            self.assertIn("src/key.pem", result.message)


class ReleaseScriptTests(unittest.TestCase):
    def test_scripts_build_invokes_release_module(self):
        script = Path("scripts/build")
        self.assertTrue(script.is_file())
        text = script.read_text(encoding="utf-8")
        self.assertIn("python3 -m nexus_harness.release", text)
        self.assertIn("PYTHONPATH", text)


if __name__ == "__main__":
    unittest.main()
