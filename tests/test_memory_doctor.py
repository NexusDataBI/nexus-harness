import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from nexus_harness.memory.doctor import memory_doctor
from nexus_harness.memory.models import (
    MemoryConfidence,
    MemoryDraft,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.store import init_project_memory, write_memory


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
