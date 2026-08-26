from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from nexus_harness.memory.capsule import load_capsule_policy
from nexus_harness.memory.freshness import FreshnessStatus, compute_memory_freshness
from nexus_harness.memory.guard import (
    MemoryGuardError,
    validate_memory_record,
    validate_memory_text,
)
from nexus_harness.memory.models import MemoryRecord, MemoryStatus
from nexus_harness.memory.portfolio import _PORTFOLIO_CATEGORIES
from nexus_harness.memory.retrieval import rebuild_index
from nexus_harness.memory.store import CATEGORY_BY_TYPE, _project_memory_root

_SECRET_FINDING = "secret_like_content"


@dataclass(frozen=True)
class MemoryDoctorFinding:
    code: str
    severity: str
    memory_id: str | None
    path: str | None
    message: str


@dataclass(frozen=True)
class MemoryDoctorReport:
    gate: str
    findings: tuple[MemoryDoctorFinding, ...]
    project_records: int
    portfolio_records: int
    stale_records: int


def memory_doctor(project_root, portfolio_root=None) -> MemoryDoctorReport:
    findings: list[MemoryDoctorFinding] = []
    loaded: list[MemoryRecord] = []
    project_root = Path(project_root)
    project_parsed, project_stale = _scan_tree(
        findings,
        _project_memory_root(project_root),
        CATEGORY_BY_TYPE.values(),
        project_root,
        loaded,
    )
    portfolio_parsed = 0
    portfolio_stale = 0
    if portfolio_root is not None:
        vault = Path(portfolio_root)
        _check_portfolio_layout(findings, vault)
        portfolio_parsed, portfolio_stale = _scan_tree(
            findings,
            vault,
            _PORTFOLIO_CATEGORIES,
            project_root,
            loaded,
        )
    _check_capsule_policy(findings)
    _check_index_rebuildable(findings, loaded)
    fail = any(item.severity == "FAIL" for item in findings)
    return MemoryDoctorReport(
        gate="FAIL" if fail else "PASS",
        findings=tuple(findings),
        project_records=project_parsed,
        portfolio_records=portfolio_parsed,
        stale_records=project_stale + portfolio_stale,
    )


def _check_portfolio_layout(findings: list[MemoryDoctorFinding], vault: Path) -> None:
    if not vault.is_dir():
        findings.append(
            MemoryDoctorFinding(
                code="missing_portfolio_layout",
                severity="FAIL",
                memory_id=None,
                path=str(vault),
                message="configured portfolio vault is missing",
            )
        )
        return
    for name in _PORTFOLIO_CATEGORIES:
        if not (vault / name).is_dir():
            findings.append(
                MemoryDoctorFinding(
                    code="missing_portfolio_layout",
                    severity="FAIL",
                    memory_id=None,
                    path=str(vault / name),
                    message="portfolio category directory is missing",
                )
            )


def _check_capsule_policy(findings: list[MemoryDoctorFinding]) -> None:
    try:
        policy = load_capsule_policy()
    except Exception:
        findings.append(
            MemoryDoctorFinding(
                code="capsule_policy",
                severity="FAIL",
                memory_id=None,
                path=None,
                message="capsule policy is unreadable",
            )
        )
        return
    if (
        min(
            policy.hot_max_chars,
            policy.warm_max_chars,
            policy.max_items,
            policy.max_item_chars,
        )
        <= 0
    ):
        findings.append(
            MemoryDoctorFinding(
                code="capsule_budget",
                severity="FAIL",
                memory_id=None,
                path=None,
                message="capsule budget is not positive",
            )
        )


def _check_index_rebuildable(
    findings: list[MemoryDoctorFinding], records: list[MemoryRecord]
) -> None:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rebuild_index(list(records), Path(tmp) / "memory.db")
    except Exception:
        findings.append(
            MemoryDoctorFinding(
                code="index_unrebuildable",
                severity="FAIL",
                memory_id=None,
                path=None,
                message="derived memory index could not be rebuilt",
            )
        )


def _invalid_related_path(value: str) -> bool:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return False
    posix = PurePosixPath(normalized)
    return posix.is_absolute() or normalized.startswith("/") or ".." in posix.parts


def _scan_tree(
    findings: list[MemoryDoctorFinding],
    root: Path,
    categories,
    project_root: Path,
    loaded: list[MemoryRecord],
) -> tuple[int, int]:
    parsed = 0
    stale = 0
    seen_ids: dict[str, list[Path]] = defaultdict(list)
    if not root.is_dir():
        findings.append(
            MemoryDoctorFinding(
                code="missing_project_layout",
                severity="FAIL",
                memory_id=None,
                path=str(root),
                message="project memory layout is missing",
            )
        )
        return 0, 0

    for category in categories:
        directory = root / category
        if not directory.is_dir():
            continue
        markdown = {
            path.stem: path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix == ".md"
            and not path.name.endswith(".tmp")
        }
        sidecars = {
            path.stem: path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix == ".json"
            and not path.name.endswith(".tmp")
        }
        for stem, md_path in sorted(markdown.items()):
            if stem not in sidecars:
                findings.append(
                    MemoryDoctorFinding(
                        code="orphan_markdown",
                        severity="FAIL",
                        memory_id=stem if stem.startswith("mem-") else None,
                        path=str(md_path),
                        message="markdown pair is missing its JSON sidecar",
                    )
                )
                _scan_text_for_secrets(
                    findings, md_path.read_text(encoding="utf-8"), stem, md_path
                )
        for stem, json_path in sorted(sidecars.items()):
            if stem not in markdown:
                findings.append(
                    MemoryDoctorFinding(
                        code="orphan_json",
                        severity="FAIL",
                        memory_id=stem if stem.startswith("mem-") else None,
                        path=str(json_path),
                        message="JSON sidecar is missing its markdown pair",
                    )
                )
            record = _load_record(findings, json_path)
            if record is None:
                continue
            parsed += 1
            loaded.append(record)
            seen_ids[record.id].append(json_path)
            _check_record(findings, record, json_path, project_root)
            if _is_stale(project_root, record):
                stale += 1
            md_path = markdown.get(stem)
            if md_path is not None:
                _scan_text_for_secrets(
                    findings,
                    md_path.read_text(encoding="utf-8"),
                    record.id,
                    md_path,
                )

    for memory_id, paths in sorted(seen_ids.items()):
        if len(paths) > 1:
            findings.append(
                MemoryDoctorFinding(
                    code="duplicate_id",
                    severity="FAIL",
                    memory_id=memory_id,
                    path=str(paths[0]),
                    message="memory id appears more than once",
                )
            )
    return parsed, stale


def _load_record(
    findings: list[MemoryDoctorFinding], path: Path
) -> MemoryRecord | None:
    try:
        text = path.read_text(encoding="utf-8")
        record = MemoryRecord.from_json_dict(json.loads(text))
    except Exception:
        findings.append(
            MemoryDoctorFinding(
                code="invalid_sidecar",
                severity="FAIL",
                memory_id=path.stem if path.stem.startswith("mem-") else None,
                path=str(path),
                message="sidecar JSON is unreadable or does not match the memory schema",
            )
        )
        return None
    return record


def _check_record(
    findings: list[MemoryDoctorFinding],
    record: MemoryRecord,
    path: Path,
    project_root: Path,
) -> None:
    try:
        validate_memory_record(record)
    except MemoryGuardError as exc:
        findings.append(
            MemoryDoctorFinding(
                code=_SECRET_FINDING,
                severity="FAIL",
                memory_id=record.id,
                path=str(path),
                message=str(exc),
            )
        )
    if record.status == MemoryStatus.VERIFIED and not record.sources:
        findings.append(
            MemoryDoctorFinding(
                code="verified_without_provenance",
                severity="FAIL",
                memory_id=record.id,
                path=str(path),
                message="VERIFIED memory requires provenance sources",
            )
        )
    if record.status == MemoryStatus.SUPERSEDED and not record.supersedes:
        findings.append(
            MemoryDoctorFinding(
                code="superseded_without_target",
                severity="FAIL",
                memory_id=record.id,
                path=str(path),
                message="SUPERSEDED memory is missing a supersedes target",
            )
        )
    if any(_invalid_related_path(related) for related in record.related_paths):
        findings.append(
            MemoryDoctorFinding(
                code="invalid_related_path",
                severity="FAIL",
                memory_id=record.id,
                path=str(path),
                message="related_paths contains an absolute or parent-directory path",
            )
        )
    if record.status == MemoryStatus.VERIFIED and _is_stale(project_root, record):
        findings.append(
            MemoryDoctorFinding(
                code="stale_status_inconsistent",
                severity="FAIL",
                memory_id=record.id,
                path=str(path),
                message="VERIFIED memory is stale against the current repository",
            )
        )


def _is_stale(project_root: Path, record: MemoryRecord) -> bool:
    if record.status == MemoryStatus.STALE:
        return True
    try:
        return (
            compute_memory_freshness(project_root, record).status
            == FreshnessStatus.STALE
        )
    except Exception:
        return False


def _scan_text_for_secrets(
    findings: list[MemoryDoctorFinding],
    text: str,
    memory_id: str | None,
    path: Path,
) -> None:
    try:
        validate_memory_text(text)
    except MemoryGuardError as exc:
        findings.append(
            MemoryDoctorFinding(
                code=_SECRET_FINDING,
                severity="FAIL",
                memory_id=memory_id,
                path=str(path),
                message=str(exc),
            )
        )
