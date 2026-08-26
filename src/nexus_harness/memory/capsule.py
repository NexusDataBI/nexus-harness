from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from nexus_harness.config import load_toml
from nexus_harness.memory.freshness import FreshnessStatus
from nexus_harness.memory.models import MemorySensitivity, MemoryStatus
from nexus_harness.memory.retrieval import MemoryHit, _hit_sort_key

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


@dataclass(frozen=True)
class CapsulePolicy:
    hot_max_chars: int
    warm_max_chars: int
    max_items: int
    max_item_chars: int
    include_stale_warnings: bool = True


@dataclass(frozen=True)
class ContextCapsule:
    project_id: str | None
    diff_hash: str | None
    hot: str
    warm: str
    warnings: str
    item_count: int
    findings: tuple[dict[str, str], ...] = ()

    @property
    def text(self) -> str:
        parts = [
            "NEXUS CONTEXT CAPSULE\n"
            f"Project: {self.project_id or 'unknown'}\n"
            f"Diff: {self.diff_hash or 'unknown'}"
        ]
        if self.hot:
            parts.append("HOT\n" + self.hot)
        if self.warm:
            parts.append("WARM\n" + self.warm)
        if self.warnings:
            parts.append("STALE/CONFLICT WARNINGS\n" + self.warnings)
        return "\n\n".join(parts).rstrip() + "\n"


def load_capsule_policy(path: Path | None = None) -> CapsulePolicy:
    data = load_toml(Path(path) if path is not None else _POLICY_PATH)
    section = data["capsule"]
    return CapsulePolicy(
        hot_max_chars=int(section["hot_max_chars"]),
        warm_max_chars=int(section["warm_max_chars"]),
        max_items=int(section["max_items"]),
        max_item_chars=int(section["max_item_chars"]),
        include_stale_warnings=bool(section.get("include_stale_warnings", True)),
    )


def build_context_capsule(
    project_id: str | None,
    diff_hash: str | None,
    hits: Sequence[MemoryHit],
    hot_memory_ids: Sequence[str],
    policy: CapsulePolicy,
    findings: Sequence[dict[str, str]] = (),
) -> ContextCapsule:
    ranked = _dedupe_ranked(hits)
    hot_ids = set(hot_memory_ids)
    used: set[str] = set()
    hot_blocks: list[str] = []
    warm_blocks: list[str] = []

    for hit in ranked:
        if len(used) >= policy.max_items:
            break
        if hit.record.id not in hot_ids or not _eligible_for_injection(hit):
            continue
        block = _render_item(hit, policy.max_item_chars)
        if _append_block(hot_blocks, block, policy.hot_max_chars):
            used.add(hit.record.id)

    for hit in ranked:
        if len(used) >= policy.max_items:
            break
        if hit.record.id in used or not _eligible_for_injection(hit):
            continue
        block = _render_item(hit, policy.max_item_chars)
        if _append_block(warm_blocks, block, policy.warm_max_chars):
            used.add(hit.record.id)

    warning_blocks: list[str] = []
    if policy.include_stale_warnings:
        for hit in ranked:
            if _eligible_for_warning(hit):
                warning_blocks.append(
                    f"- {hit.record.id} was excluded because it is stale."
                )
    for finding in findings:
        if finding.get("code") == "memory_contradiction":
            pointer = finding.get("pointer", "")
            suffix = f" ({pointer})" if pointer else ""
            warning_blocks.append(
                f"- {finding.get('memory_id', 'memory record')} was excluded because "
                f"it contradicts {finding.get('authority', 'CURRENT_REPO')}{suffix}."
            )
        else:
            warning_blocks.append(
                f"- {finding.get('path', 'memory record')} was excluded because its "
                "sidecar is invalid."
            )

    return ContextCapsule(
        project_id=project_id,
        diff_hash=diff_hash,
        hot="\n".join(hot_blocks),
        warm="\n".join(warm_blocks),
        warnings="\n".join(warning_blocks),
        item_count=len(used),
        findings=tuple(findings),
    )


def _dedupe_ranked(hits: Iterable[MemoryHit]) -> list[MemoryHit]:
    ordered: list[MemoryHit] = []
    seen: set[str] = set()
    for hit in sorted(hits, key=_hit_sort_key):
        if hit.record.id in seen:
            continue
        seen.add(hit.record.id)
        ordered.append(hit)
    return ordered


def _is_stale(hit: MemoryHit) -> bool:
    return (
        hit.freshness == FreshnessStatus.STALE
        or hit.record.status == MemoryStatus.STALE
    )


def _is_confidential(hit: MemoryHit) -> bool:
    return hit.record.sensitivity == MemorySensitivity.CONFIDENTIAL


def _eligible_for_injection(hit: MemoryHit) -> bool:
    return (
        hit.record.status == MemoryStatus.VERIFIED
        and not _is_confidential(hit)
        and not _is_stale(hit)
    )


def _eligible_for_warning(hit: MemoryHit) -> bool:
    if _is_confidential(hit) or hit.record.status in _EXCLUDED_STATUSES:
        return False
    return _is_stale(hit)


def _clip_body(body: str, max_chars: int) -> str:
    if max_chars <= 0:
        return "…"
    if len(body) <= max_chars:
        return body
    window = body[:max_chars]
    cut = None
    for index in range(len(window) - 1, -1, -1):
        if window[index].isspace():
            cut = index
            break
    excerpt = window[:cut].rstrip() if cut else window.rstrip()
    return f"{excerpt}…"


def _render_item(hit: MemoryHit, max_item_chars: int) -> str:
    excerpt = _clip_body(hit.record.body, max_item_chars)
    indented = "\n".join(f"  {line}" for line in (excerpt.splitlines() or [""]))
    return (
        f"- [{hit.record.type.value.upper()}] {hit.record.title}\n"
        f"{indented}\n"
        f"  source: {hit.record.id} | freshness: {hit.freshness}"
    )


def _append_block(blocks: list[str], block: str, limit: int) -> bool:
    proposed = block if not blocks else "\n".join(blocks) + "\n" + block
    if len(proposed) > limit:
        return False
    blocks.append(block)
    return True
