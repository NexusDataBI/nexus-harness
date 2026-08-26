from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from nexus_harness.config import load_toml
from nexus_harness.memory.freshness import (
    FreshnessResult,
    FreshnessStatus,
    TruthStrength,
    compute_memory_freshness,
)
from nexus_harness.memory.models import (
    MemoryRecord,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
    MemoryType,
)
from nexus_harness.memory.portfolio import (
    load_portfolio_memories,
    load_portfolio_memories_tolerant,
)
from nexus_harness.memory.store import (
    load_project_memories,
    load_project_memories_tolerant,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_POLICY_PATH = _REPO_ROOT / "core" / "memory" / "retrieval-policy.toml"
_EXCLUDED_STATUSES = frozenset(
    {
        MemoryStatus.CANDIDATE,
        MemoryStatus.SUPERSEDED,
        MemoryStatus.REJECTED,
        MemoryStatus.ARCHIVED,
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
_SAFE_REPO_ID = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class MemoryQueryContext:
    project_id: str | None
    affected_paths: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    requested_types: tuple[MemoryType, ...] = ()
    include_stale: bool = False


@dataclass(frozen=True)
class MemoryHit:
    record: MemoryRecord
    score: int
    freshness: FreshnessStatus
    reasons: tuple[str, ...]


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(_TOKEN_RE.findall(text.lower()))))


def default_index_path(repo_id: str, cache_home: Path | None = None) -> Path:
    safe_id = _SAFE_REPO_ID.sub("-", repo_id).strip(".-") or "default"
    base = cache_home or Path.home() / ".nexus-harness" / "memory-cache"
    return Path(base) / safe_id / "memory.db"


def fts5_available(connection: sqlite3.Connection | None = None) -> bool:
    own = connection is None
    conn = connection or sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE temp._nexus_fts5_probe USING fts5(content)")
        conn.execute("DROP TABLE IF EXISTS temp._nexus_fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        if own:
            conn.close()


def rebuild_index(records: list[MemoryRecord], db_path: Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        (
            record.id,
            record.project_id or "",
            record.type.value,
            record.title,
            record.body,
            " ".join(record.tags),
        )
        for record in records
    ]
    conn = sqlite3.connect(db_path)
    try:
        if fts5_available(conn):
            conn.execute("DROP TABLE IF EXISTS memory_fts")
            conn.execute(
                "CREATE VIRTUAL TABLE memory_fts USING fts5("
                "id UNINDEXED, project_id UNINDEXED, type UNINDEXED, title, body, tags)"
            )
            conn.executemany(
                "INSERT INTO memory_fts(id, project_id, type, title, body, tags) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
        else:
            conn.execute("DROP TABLE IF EXISTS memory_lex")
            conn.execute(
                "CREATE TABLE memory_lex ("
                "id TEXT PRIMARY KEY, project_id TEXT, type TEXT, "
                "title TEXT, body TEXT, tags TEXT)"
            )
            conn.executemany(
                "INSERT INTO memory_lex(id, project_id, type, title, body, tags) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
        conn.commit()
    finally:
        conn.close()


def search_memory(
    project_root: Path,
    query: str,
    context: MemoryQueryContext,
    *,
    portfolio_root: Path | None = None,
    cache_home: Path | None = None,
    findings: list[dict[str, str]] | None = None,
) -> list[MemoryHit]:
    load = (
        load_project_memories_tolerant
        if findings is not None
        else load_project_memories
    )
    records = list(
        load(project_root, findings) if findings is not None else load(project_root)
    )
    if portfolio_root is not None:
        portfolio_load = (
            load_portfolio_memories_tolerant
            if findings is not None
            else load_portfolio_memories
        )
        records.extend(
            portfolio_load(portfolio_root, findings)
            if findings is not None
            else portfolio_load(portfolio_root)
        )

    eligible = [record for record in records if _is_eligible(record, context)]
    fts_ids: set[str] = set()
    db_path = default_index_path(context.project_id or "default", cache_home=cache_home)
    if fts5_available():
        try:
            rebuild_index(records, db_path)
            fts_ids = set(_fts_match_ids(db_path, query))
        except (OSError, sqlite3.Error):
            fts_ids = set()

    hits: list[MemoryHit] = []
    for record in eligible:
        freshness = _freshness_for(project_root, record)
        if freshness.status == FreshnessStatus.STALE and not context.include_stale:
            continue
        score, reasons = _score_record(
            record, query, context, freshness.status, fts_matched=record.id in fts_ids
        )
        hits.append(
            MemoryHit(
                record=record,
                score=score,
                freshness=freshness.status,
                reasons=tuple(reasons),
            )
        )
    hits.sort(key=_hit_sort_key)
    return hits[:50]


def _is_eligible(record: MemoryRecord, context: MemoryQueryContext) -> bool:
    if record.status in _EXCLUDED_STATUSES:
        return False
    if record.status == MemoryStatus.STALE and not context.include_stale:
        return False
    if record.sensitivity == MemorySensitivity.CONFIDENTIAL:
        return False
    return True


def _freshness_for(project_root: Path, record: MemoryRecord) -> FreshnessResult:
    if record.scope != MemoryScope.PROJECT:
        return FreshnessResult(FreshnessStatus.UNKNOWN, ("non_project_scope",))
    return compute_memory_freshness(project_root, record)


def _weights() -> dict:
    return load_toml(_POLICY_PATH)["weights"]


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/")


def _path_matches(changed_path: str, pattern: str) -> bool:
    changed = _normalize_path(changed_path)
    normalized = _normalize_path(pattern)
    if normalized.endswith("/**"):
        prefix = normalized[:-3]
        if changed == prefix or changed.startswith(prefix + "/"):
            return True
    if changed == normalized:
        return True
    return PurePosixPath(changed).match(normalized)


def _path_bonus(
    record: MemoryRecord, context: MemoryQueryContext, weights: dict
) -> int:
    if not record.related_paths or not context.affected_paths:
        return 0
    exact = False
    prefix = False
    for related in record.related_paths:
        related_norm = _normalize_path(related)
        for affected in context.affected_paths:
            affected_norm = _normalize_path(affected)
            if affected_norm == related_norm:
                exact = True
            elif _path_matches(affected_norm, related_norm):
                prefix = True
    if exact:
        return int(weights["exact_path"])
    if prefix:
        return int(weights["path_prefix"])
    return 0


def _score_record(
    record: MemoryRecord,
    query: str,
    context: MemoryQueryContext,
    freshness: FreshnessStatus,
    *,
    fts_matched: bool = False,
) -> tuple[int, list[str]]:
    weights = _weights()
    score = 0
    reasons: list[str] = []
    if context.project_id and record.project_id == context.project_id:
        score += int(weights["same_project"])
        reasons.append("same_project")

    path_score = _path_bonus(record, context, weights)
    if path_score:
        score += path_score
        reasons.append(
            "exact_path" if path_score == int(weights["exact_path"]) else "path_prefix"
        )

    tag_hits = sum(1 for tag in context.tags if tag in record.tags)
    if tag_hits:
        score += min(
            tag_hits * int(weights["exact_tag"]), int(weights["exact_tag_cap"])
        )
        reasons.append("exact_tag")

    query_tokens = set(tokenize(query))
    title_hits = len(query_tokens & set(tokenize(record.title)))
    if title_hits:
        score += min(
            title_hits * int(weights["title_token"]), int(weights["title_token_cap"])
        )
        reasons.append("title_token")
    body_hits = len(query_tokens & set(tokenize(record.body)))
    if body_hits:
        score += min(
            body_hits * int(weights["body_token"]), int(weights["body_token_cap"])
        )
        reasons.append("body_token")

    if context.requested_types and record.type in context.requested_types:
        score += int(weights["requested_type"])
        reasons.append("requested_type")

    if record.status == MemoryStatus.VERIFIED:
        if freshness == FreshnessStatus.FRESH:
            score += int(weights["verified_fresh"])
            reasons.append("verified_fresh")
        elif freshness == FreshnessStatus.UNKNOWN:
            score += int(weights["verified_unknown"])
            reasons.append("verified_unknown")

    if freshness == FreshnessStatus.STALE or record.status == MemoryStatus.STALE:
        score += int(weights["stale"])
        reasons.append("stale")

    if fts_matched:
        reasons.append("fts_match")

    return score, reasons


def _provenance_strength(record: MemoryRecord, freshness: FreshnessStatus) -> int:
    if record.status == MemoryStatus.STALE or freshness == FreshnessStatus.STALE:
        return int(TruthStrength.STALE_MEMORY)
    if record.scope == MemoryScope.PORTFOLIO:
        return int(TruthStrength.VERIFIED_PORTFOLIO_MEMORY)
    return int(TruthStrength.VERIFIED_PROJECT_MEMORY)


def _hit_sort_key(hit: MemoryHit) -> tuple:
    verified = hit.record.verified_at or ""
    return (
        -hit.score,
        -_provenance_strength(hit.record, hit.freshness),
        0 if verified else 1,
        tuple(-ord(character) for character in verified),
        hit.record.id,
    )


def _fts_match_ids(db_path: Path, query: str) -> list[str]:
    tokens = tokenize(query)
    if not tokens:
        return []
    match = " OR ".join(tokens)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id FROM memory_fts WHERE memory_fts MATCH ?",
            (match,),
        ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]
