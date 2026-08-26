import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from nexus_harness.memory.doctor import memory_doctor
from nexus_harness.memory.lifecycle import supersede_memory
from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.store import init_project_memory, write_memory
from tests.memory_git_helper import make_repo_with_changed_file


def _candidate(**overrides) -> MemoryDraft:
    payload = {
        "type": MemoryType.INVARIANT,
        "scope": MemoryScope.PROJECT,
        "project_id": "repo-1",
        "title": "Auth sessions stay isolated",
        "body": "Session cookies must not leak across tenants.",
    }
    payload.update(overrides)
    return MemoryDraft(**payload)


def _finding_codes(report) -> list[str]:
    return [finding.code for finding in report.findings]


def _report_text(report) -> str:
    parts = [report.gate]
    for finding in report.findings:
        parts.extend(
            [
                finding.code,
                finding.severity,
                finding.memory_id or "",
                finding.path or "",
                finding.message,
            ]
        )
    return "\n".join(parts)


class MemoryDoctorTests(unittest.TestCase):
    def test_clean_initialized_memory_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory_root = init_project_memory(root)
            before = sorted(path.stat().st_mtime_ns for path in memory_root.rglob("*"))

            report = memory_doctor(root)

            self.assertEqual(report.gate, "PASS")
            self.assertEqual(report.findings, ())
            self.assertEqual(report.project_records, 0)
            self.assertEqual(report.portfolio_records, 0)
            self.assertEqual(report.stale_records, 0)
            after = sorted(path.stat().st_mtime_ns for path in memory_root.rglob("*"))
            self.assertEqual(after, before)

    def test_orphan_markdown_without_json_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            orphan = root / ".nexus" / "memory" / "invariants" / "mem-orphan.md"
            orphan.write_text("# Orphan note\n", encoding="utf-8")

            report = memory_doctor(root)

            self.assertEqual(report.gate, "FAIL")
            self.assertIn("orphan_markdown", _finding_codes(report))
            finding = next(
                item for item in report.findings if item.code == "orphan_markdown"
            )
            self.assertEqual(finding.severity, "FAIL")
            self.assertTrue(str(finding.path).endswith("mem-orphan.md"))

    def test_duplicate_memory_id_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = write_memory(root, _candidate().to_record())
            duplicate_dir = root / ".nexus" / "memory" / "lessons"
            (duplicate_dir / f"{record.id}.md").write_text("# Dup\n", encoding="utf-8")
            payload = record.to_json_dict()
            payload["type"] = MemoryType.LESSON.value
            (duplicate_dir / f"{record.id}.json").write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )

            report = memory_doctor(root)

            self.assertEqual(report.gate, "FAIL")
            self.assertIn("duplicate_id", _finding_codes(report))
            finding = next(
                item for item in report.findings if item.code == "duplicate_id"
            )
            self.assertEqual(finding.severity, "FAIL")
            self.assertEqual(finding.memory_id, record.id)

    def test_verified_sidecar_without_provenance_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = replace(
                _candidate().to_record(),
                status=MemoryStatus.VERIFIED,
                confidence=MemoryConfidence.HIGH,
                verified_at="2026-08-25T00:00:00Z",
                valid_at_commit="abc123",
                sources=(),
            )
            write_memory(root, record)

            report = memory_doctor(root)

            self.assertEqual(report.gate, "FAIL")
            self.assertIn("verified_without_provenance", _finding_codes(report))
            finding = next(
                item
                for item in report.findings
                if item.code == "verified_without_provenance"
            )
            self.assertEqual(finding.severity, "FAIL")
            self.assertEqual(finding.memory_id, record.id)

    def test_candidate_without_provenance_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = write_memory(root, _candidate(sources=()).to_record())

            report = memory_doctor(root)

            self.assertEqual(report.gate, "PASS")
            self.assertNotIn("verified_without_provenance", _finding_codes(report))
            self.assertEqual(report.project_records, 1)
            self.assertEqual(record.status, MemoryStatus.CANDIDATE)
            self.assertEqual(record.sources, ())

    def test_secret_like_content_fails_without_echoing_secret(self):
        secret = "ghp_abcdefghijklmnopqrstuvwxyz01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            memory_id = "mem-invariant-leaked-deadbeef"
            category = root / ".nexus" / "memory" / "invariants"
            (category / f"{memory_id}.md").write_text(
                f"# Leaked\n\ndo not store {secret}\n",
                encoding="utf-8",
            )
            payload = replace(
                _candidate(title="Leaked").to_record(memory_id=memory_id),
                body=f"do not store {secret}",
            ).to_json_dict()
            (category / f"{memory_id}.json").write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )

            report = memory_doctor(root)

            self.assertEqual(report.gate, "FAIL")
            self.assertTrue(
                any(
                    item.severity == "FAIL" and "secret" in item.code
                    for item in report.findings
                )
            )
            self.assertNotIn(secret, _report_text(report))
            for finding in report.findings:
                self.assertNotIn(secret, finding.message)
                self.assertNotIn("abcdefghijklmnopqrstuvwxyz01", finding.message)

    def test_superseded_without_target_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = write_memory(root, _candidate().to_record())
            write_memory(
                root,
                replace(record, status=MemoryStatus.SUPERSEDED, supersedes=()),
                replace=True,
            )

            report = memory_doctor(root)

            self.assertEqual(report.gate, "FAIL")
            self.assertIn("superseded_without_target", _finding_codes(report))
            finding = next(
                item
                for item in report.findings
                if item.code == "superseded_without_target"
            )
            self.assertEqual(finding.severity, "FAIL")
            self.assertEqual(finding.memory_id, record.id)

    def test_supersede_memory_with_incoming_replacement_link_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            old = write_memory(root, _candidate(title="Old rule").to_record())
            replacement = write_memory(
                root,
                replace(
                    _candidate(title="Replacement rule").to_record(),
                    supersedes=(old.id,),
                ),
            )

            supersede_memory(root, old.id, replacement.id)
            report = memory_doctor(root)

            old_findings = [
                finding
                for finding in report.findings
                if finding.memory_id == old.id
                and finding.code == "superseded_without_target"
            ]
            self.assertEqual(old_findings, [])

    def test_superseded_with_outgoing_link_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = replace(
                _candidate(title="Old rule").to_record(),
                status=MemoryStatus.SUPERSEDED,
                supersedes=("mem-invariant-replacement-deadbeef",),
            )
            write_memory(root, record)

            report = memory_doctor(root)

            self.assertNotIn("superseded_without_target", _finding_codes(report))

    def test_verified_stale_status_is_inconsistent(self):
        root, commit_a = make_repo_with_changed_file("src/auth.py")
        init_project_memory(root)
        record = replace(
            _candidate(
                related_paths=("src/auth.py",),
                sources=(MemorySource("approved_spec", "SPEC-AUTH"),),
            ).to_record(),
            status=MemoryStatus.VERIFIED,
            confidence=MemoryConfidence.HIGH,
            verified_at="2026-08-25T00:00:00Z",
            valid_at_commit=commit_a,
        )
        write_memory(root, record)

        report = memory_doctor(root)

        self.assertEqual(report.gate, "FAIL")
        self.assertIn("stale_status_inconsistent", _finding_codes(report))
        finding = next(
            item for item in report.findings if item.code == "stale_status_inconsistent"
        )
        self.assertEqual(finding.severity, "FAIL")
        self.assertEqual(finding.memory_id, record.id)
        self.assertGreaterEqual(report.stale_records, 1)

    def test_invalid_related_path_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            traversal = write_memory(
                root,
                _candidate(
                    title="Parent traversal path",
                    related_paths=("../../etc/passwd",),
                ).to_record(),
            )
            absolute = write_memory(
                root,
                _candidate(
                    title="Absolute home path",
                    related_paths=("/Users/someone/secret",),
                ).to_record(),
            )

            report = memory_doctor(root)

            self.assertEqual(report.gate, "FAIL")
            codes = _finding_codes(report)
            self.assertGreaterEqual(codes.count("invalid_related_path"), 2)
            ids = {
                item.memory_id
                for item in report.findings
                if item.code == "invalid_related_path"
            }
            self.assertEqual(ids, {traversal.id, absolute.id})
            for finding in report.findings:
                self.assertEqual(finding.severity, "FAIL")
                self.assertNotIn("someone", finding.message)

    def test_glob_related_path_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            write_memory(root, _candidate(related_paths=("src/auth/**",)).to_record())

            report = memory_doctor(root)

            self.assertEqual(report.gate, "PASS")
            self.assertNotIn("invalid_related_path", _finding_codes(report))

    def test_index_rebuild_failure_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            write_memory(root, _candidate().to_record())

            with patch(
                "nexus_harness.memory.doctor.rebuild_index",
                side_effect=OSError("index write failed"),
            ):
                report = memory_doctor(root)

            self.assertEqual(report.gate, "FAIL")
            self.assertIn("index_unrebuildable", _finding_codes(report))
            finding = next(
                item for item in report.findings if item.code == "index_unrebuildable"
            )
            self.assertEqual(finding.severity, "FAIL")
            self.assertNotIn("index write failed", finding.message)
