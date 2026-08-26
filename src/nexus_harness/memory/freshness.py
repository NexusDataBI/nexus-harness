from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path, PurePosixPath

from nexus_harness.memory.models import MemoryRecord, MemoryStatus
from nexus_harness.safe import verify_git_oid


class FreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FreshnessResult:
    status: FreshnessStatus
    reasons: tuple[str, ...]
    changed_paths: tuple[str, ...] = ()


class TruthStrength(IntEnum):
    CURRENT_INSTRUCTION = 900
    HARD_POLICY = 850
    FRESH_EXECUTABLE_EVIDENCE = 800
    CURRENT_REPO = 750
    CANONICAL_DOC = 700
    WORK_RECORD = 650
    VERIFIED_PROJECT_MEMORY = 500
    VERIFIED_PORTFOLIO_MEMORY = 450
    STALE_MEMORY = 100
    SESSION_RECOLLECTION = 50


@dataclass(frozen=True)
class AuthorityContradiction:
    """Caller-supplied higher-authority claim; never inferred by retrieval."""

    memory_id: str
    authority: TruthStrength = TruthStrength.CURRENT_REPO
    pointer: str = ""


@dataclass(frozen=True)
class ContradictionResolution:
    winner: str | None
    excluded: tuple[str, ...]
    requires_adjudication: bool
    reason: str


def _path_matches(changed_path: str, pattern: str) -> bool:
    changed = changed_path.replace("\\", "/")
    normalized = pattern.replace("\\", "/")
    if normalized.endswith("/**"):
        prefix = normalized[:-3]
        if changed == prefix or changed.startswith(prefix + "/"):
            return True
    if changed == normalized:
        return True
    return PurePosixPath(changed).match(normalized)


def _changed_paths_since(
    repo_root: Path, valid_at_commit: str
) -> tuple[str, ...] | None:
    try:
        oid = verify_git_oid(repo_root, valid_at_commit)
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only", f"{oid}..HEAD", "--"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, ValueError):
        return None
    return tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())


def compute_memory_freshness(repo_root: Path, record: MemoryRecord) -> FreshnessResult:
    if record.status != MemoryStatus.VERIFIED:
        return FreshnessResult(FreshnessStatus.UNKNOWN, ("status_not_verified",))
    if not record.valid_at_commit:
        return FreshnessResult(FreshnessStatus.UNKNOWN, ("missing_valid_at_commit",))
    if not record.related_paths:
        return FreshnessResult(FreshnessStatus.UNKNOWN, ("no_related_paths",))

    changed = _changed_paths_since(repo_root, record.valid_at_commit)
    if changed is None:
        return FreshnessResult(FreshnessStatus.UNKNOWN, ("unreachable_commit",))

    overlapping = tuple(
        path
        for path in changed
        if any(_path_matches(path, pattern) for pattern in record.related_paths)
    )
    if overlapping:
        return FreshnessResult(
            FreshnessStatus.STALE,
            ("related_path_changed",),
            overlapping,
        )
    return FreshnessResult(FreshnessStatus.FRESH, ())


def resolve_contradiction(
    items: list[tuple[str, TruthStrength]],
) -> ContradictionResolution:
    if not items:
        return ContradictionResolution(
            winner=None,
            excluded=(),
            requires_adjudication=False,
            reason="empty",
        )

    strongest = max(strength for _identity, strength in items)
    leaders = [identity for identity, strength in items if strength == strongest]
    weaker = tuple(identity for identity, strength in items if strength < strongest)
    if len(leaders) != 1:
        return ContradictionResolution(
            winner=None,
            excluded=weaker,
            requires_adjudication=True,
            reason="tied_strongest",
        )
    winner = leaders[0]
    excluded = tuple(identity for identity, _strength in items if identity != winner)
    return ContradictionResolution(
        winner=winner,
        excluded=excluded,
        requires_adjudication=False,
        reason="unique_strongest",
    )
