import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from nexus_harness.migration_report import (
    EXPECTED_ARCHIVE_SHA256,
    build_migration_report,
    write_migration_report,
)
from nexus_harness.validate import CANONICAL_SKILL_NAMES

REPO_ROOT = Path(__file__).resolve().parents[1]

REMOVED_CONFIG_CLASSES = (
    "Hardcoded model routing",
    "Project-specific client rules",
    "VPS IP/SSH commands",
    "Absolute project directories",
    "Acelera/client automatic deployment rules",
    "Claude environment variables inside Codex configuration",
    "Disabled Cursor sandbox",
    "Global allow-everything command policy",
    "Mandatory Matt seven-phase lifecycle",
    "Compaction that duplicates constitution instead of restoring structured task state",
    "Bidirectional/blocked harness-sync",
)

DIVERGENT_SKILLS = (
    "code-review",
    "impeccable",
    "implement",
    "napkin",
    "root-cause-tracing",
    "tdd-workflow",
    "token-optimizer",
    "ui-ux-pro-max",
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_migration_docs(
    root: Path, *, archive_sha: str, ledger: list[dict]
) -> None:
    _write(
        root / "docs/migration/v3-baseline.json",
        json.dumps(
            {
                "appledouble_count": 0,
                "duplicate_file_count": 4,
                "file_count": 10,
                "redundant_bytes": 40,
                "source_archive_sha256": archive_sha,
                "total_bytes": 100,
            },
            indent=2,
        )
        + "\n",
    )
    _write(
        root / "docs/migration/cleanup-report.json",
        json.dumps(
            {
                "before": {
                    "duplicate_file_count": 4,
                    "file_count": 10,
                    "redundant_bytes": 40,
                    "total_bytes": 100,
                },
                "after": {
                    "duplicate_file_count": 2,
                    "file_count": 8,
                    "redundant_bytes": 20,
                    "total_bytes": 80,
                },
            },
            indent=2,
        )
        + "\n",
    )
    _write(
        root / "docs/migration/skill-ledger.json",
        json.dumps(ledger, indent=2) + "\n",
    )
    _write(
        root / "docs/migration/unique-heuristics.md",
        "# Unique heuristics\n\n"
        "Unresolved divergent decisions = 0.\n\n"
        "| Source | Relationship | Status |\n"
        "| --- | --- | --- |\n"
        "| `napkin` | divergent | DISCARDED_WITH_REASON: operator note. |\n",
    )
    _write(
        root / "docs/migration/debt.json",
        json.dumps(
            {
                "schema_version": 1,
                "items": [
                    {"id": "P1-D05", "status": "resolved"},
                    {"id": "P8-A01", "status": "accepted_residual"},
                ],
            },
            indent=2,
        )
        + "\n",
    )
    _write(
        root / "docs/MIGRATION-MAP.md",
        "# Migration Map\n\n"
        "## Remove from global configuration\n\n"
        + "\n".join(f"- {item}." for item in REMOVED_CONFIG_CLASSES)
        + "\n\n## Delete only after evidence\n\n- AppleDouble.\n",
    )
    _write(root / "core/constitution.md", "NEXUS WORKFLOW IS MANDATORY.\n")
    _write(root / "core/security/policy.toml", "schema_version = 1\n")
    _write(root / "skills/nexus-frontend/SKILL.md", "frontend\n")
    _write(root / "skills/nexus-ship/SKILL.md", "ship\n")
    _write(root / "src/nexus_harness/security.py", "security-module\n")
    _write(root / "src/nexus_harness/runtime_claude.py", "claude-adapter\n")
    _write(root / "src/nexus_harness/memory/capsule.py", "memory-capsule\n")
    _write(root / "src/nexus_harness/ci.py", "ci-module\n")
    _write(root / "src/nexus_harness/github.py", "github-module\n")
    _write(root / "src/nexus_harness/visual.py", "visual-module\n")
    _write(root / "src/nexus_harness/posthog.py", "posthog-module\n")
    _write(
        root / "harness.lock",
        json.dumps(
            {
                "generated_hashes": {"dist/a": "aa"},
                "engine_hashes": {"dist/src/x": "bb"},
            }
        )
        + "\n",
    )


def _ledger_with_divergent() -> list[dict]:
    return [
        {
            "decision": "canonicalize",
            "name": "nexus-frontend",
            "relationship": "exact_duplicate",
            "sources": ["claude/skills/nexus-frontend/SKILL.md"],
            "target": "skills/nexus-frontend/SKILL.md",
        },
        {
            "decision": "merge",
            "name": "code-review",
            "rationale": "merge unique review heuristics",
            "relationship": "divergent",
            "sources": [
                "claude/skills/code-review/SKILL.md",
                "codex/skills/code-review/SKILL.md",
            ],
            "target": "skills/nexus-quality/SKILL.md",
        },
        {
            "decision": "reference",
            "name": "napkin",
            "rationale": "localized copy; reference only",
            "relationship": "divergent",
            "sources": ["claude/skills/napkin/SKILL.md"],
            "target": None,
        },
    ]


class MigrationReportModelTests(unittest.TestCase):
    def test_report_model_includes_required_fields_from_frozen_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frozen = "aa" * 32
            _minimal_migration_docs(
                root, archive_sha=frozen, ledger=_ledger_with_divergent()
            )
            _write(root / "core/a.txt", "same")
            _write(root / "dist/a.txt", "same")
            _write(root / "skills/dup-a.md", "maintained")
            _write(root / "skills/dup-b.md", "maintained")

            report = build_migration_report(root)

            self.assertEqual(report["source_archive_sha256"], frozen)
            self.assertEqual(report["source_archive_sha_source"], "frozen-baseline")
            self.assertFalse(report["archive_present"])
            self.assertTrue(report["archive_limitation"])
            self.assertIn("unavailable", report["archive_limitation"].lower())
            self.assertEqual(report["before"]["file_count"], 10)
            self.assertEqual(report["before"]["duplicate_file_count"], 4)
            self.assertEqual(report["before"]["redundant_bytes"], 40)
            self.assertGreater(report["after"]["file_count"], 0)
            self.assertIn("duplicate_file_count", report["after"])
            self.assertIn("redundant_bytes", report["after"])
            self.assertEqual(report["after"]["generated_duplicate_count"], 1)
            self.assertEqual(report["after"]["maintained_duplicate_count"], 1)
            self.assertEqual(
                report["canonical_skills"],
                ["nexus-frontend", "nexus-ship"],
            )
            self.assertEqual(report["canonical_skill_count"], 2)
            for item in REMOVED_CONFIG_CLASSES:
                self.assertIn(
                    item, report["removed_global_project_specific_config_classes"]
                )
            self.assertEqual(report["unresolved_divergent_skill_decisions"], 0)

    def test_missing_archive_does_not_invent_a_computed_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frozen = EXPECTED_ARCHIVE_SHA256
            _minimal_migration_docs(
                root, archive_sha=frozen, ledger=_ledger_with_divergent()
            )

            report = build_migration_report(root)

            self.assertEqual(report["source_archive_sha_source"], "frozen-baseline")
            self.assertFalse(report["archive_present"])
            self.assertTrue(report["archive_unchanged"])
            self.assertEqual(report["source_archive_sha256"], EXPECTED_ARCHIVE_SHA256)

    def test_present_archive_computes_sha_and_confirms_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b"v3-export-bytes"
            digest = sha256(payload).hexdigest()
            _minimal_migration_docs(
                root, archive_sha=digest, ledger=_ledger_with_divergent()
            )
            archive = root / "inputs" / "nexus-harness-export-20260825-094238.tar.gz"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(payload)

            report = build_migration_report(root, expected_archive_sha256=digest)

            self.assertTrue(report["archive_present"])
            self.assertEqual(report["source_archive_sha_source"], "computed")
            self.assertEqual(report["source_archive_sha256"], digest)
            self.assertTrue(report["archive_unchanged"])
            self.assertIsNone(report["archive_limitation"])

    def test_reports_every_skill_ledger_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = _ledger_with_divergent()
            _minimal_migration_docs(root, archive_sha="bb" * 32, ledger=ledger)

            report = build_migration_report(root)
            names = [item["name"] for item in report["skill_ledger_decisions"]]

            self.assertEqual(names, ["code-review", "napkin", "nexus-frontend"])
            divergent = {
                item["name"]: item for item in report["divergent_skill_decisions"]
            }
            self.assertEqual(set(divergent), {"code-review", "napkin"})
            self.assertEqual(divergent["code-review"]["decision"], "merge")
            self.assertEqual(report["unresolved_divergent_skill_decisions"], 0)

    def test_generated_artifacts_count_comes_from_lock_and_dist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_migration_docs(
                root, archive_sha="cc" * 32, ledger=_ledger_with_divergent()
            )
            _write(root / "dist/hooks/nexus_event.py", "wrapper\n")

            report = build_migration_report(root)

            self.assertEqual(report["generated_artifacts_count"], 2)
            self.assertEqual(report["materialized_generated_count"], 1)

    def test_debt_and_additions_are_derived(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_migration_docs(
                root, archive_sha="dd" * 32, ledger=_ledger_with_divergent()
            )

            report = build_migration_report(root)

            self.assertEqual(report["debt"]["resolved"], ["P1-D05"])
            self.assertEqual(report["debt"]["accepted_residual"], ["P8-A01"])
            self.assertEqual(report["debt"]["unresolved"], [])
            self.assertTrue(report["security_cleanup"])
            self.assertTrue(report["runtime_adapters"])
            self.assertTrue(report["memory"])
            self.assertTrue(report["ci"])
            self.assertTrue(report["github"])
            self.assertTrue(report["frontend"])
            self.assertTrue(report["posthog"])

    def test_write_migration_report_renders_required_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_migration_docs(
                root, archive_sha="ee" * 32, ledger=_ledger_with_divergent()
            )
            destination = root / "docs/migration/final-report.md"

            payload = write_migration_report(root, destination)
            text = destination.read_text(encoding="utf-8")

            self.assertEqual(payload["before"]["file_count"], 10)
            self.assertIn("ee" * 32, text)
            self.assertIn("unresolved divergent-skill decisions: 0", text.lower())
            self.assertIn("nexus-frontend", text)
            self.assertIn("Hardcoded model routing", text)


class RepoMigrationReportTests(unittest.TestCase):
    def test_repo_report_matches_frozen_baseline_and_zero_unresolved(self):
        report = build_migration_report(REPO_ROOT)
        baseline = json.loads(
            (REPO_ROOT / "docs/migration/v3-baseline.json").read_text(encoding="utf-8")
        )
        ledger = json.loads(
            (REPO_ROOT / "docs/migration/skill-ledger.json").read_text(encoding="utf-8")
        )
        debt = json.loads(
            (REPO_ROOT / "docs/migration/debt.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            report["source_archive_sha256"],
            EXPECTED_ARCHIVE_SHA256,
        )
        self.assertEqual(report["expected_archive_sha256"], EXPECTED_ARCHIVE_SHA256)
        self.assertTrue(report["archive_unchanged"])
        self.assertEqual(report["before"]["file_count"], baseline["file_count"])
        self.assertEqual(
            report["before"]["duplicate_file_count"],
            baseline["duplicate_file_count"],
        )
        self.assertEqual(
            report["before"]["redundant_bytes"], baseline["redundant_bytes"]
        )
        self.assertGreater(report["after"]["file_count"], 0)
        self.assertLess(report["after"]["file_count"], report["before"]["file_count"])
        self.assertEqual(
            report["canonical_skills"],
            sorted(CANONICAL_SKILL_NAMES),
        )
        self.assertEqual(report["canonical_skill_count"], len(CANONICAL_SKILL_NAMES))
        self.assertEqual(report["unresolved_divergent_skill_decisions"], 0)
        self.assertEqual(len(report["skill_ledger_decisions"]), len(ledger))
        self.assertEqual(
            {item["name"] for item in report["divergent_skill_decisions"]},
            set(DIVERGENT_SKILLS),
        )
        for item in REMOVED_CONFIG_CLASSES:
            self.assertIn(
                item,
                report["removed_global_project_specific_config_classes"],
            )
        self.assertEqual(
            report["debt"]["resolved"],
            [item["id"] for item in debt["items"] if item["status"] == "resolved"],
        )
        self.assertEqual(
            report["debt"]["accepted_residual"],
            [
                item["id"]
                for item in debt["items"]
                if item["status"] == "accepted_residual"
            ],
        )
        self.assertEqual(report["debt"]["unresolved"], [])
        self.assertGreater(report["generated_artifacts_count"], 0)


if __name__ == "__main__":
    unittest.main()
