import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class MemoryStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    VERIFIED = "VERIFIED"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class MemoryType(StrEnum):
    DECISION = "decision"
    INVARIANT = "invariant"
    COMPONENT = "component"
    PATTERN = "pattern"
    LESSON = "lesson"
    INCIDENT = "incident"


class MemoryScope(StrEnum):
    PROJECT = "project"
    PORTFOLIO = "portfolio"


class MemorySensitivity(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"


class MemoryConfidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class MemorySource:
    kind: str
    ref: str


@dataclass(frozen=True)
class MemoryDraft:
    type: MemoryType
    scope: MemoryScope
    project_id: str | None
    title: str
    body: str
    sources: tuple[MemorySource, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    related_paths: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    sensitivity: MemorySensitivity = MemorySensitivity.INTERNAL

    def suggested_id(self) -> str:
        normalized_title = re.sub(r"\s+", " ", self.title.strip().lower())
        identity = "\n".join(
            (
                self.scope.value,
                self.project_id or "",
                self.type.value,
                normalized_title,
            )
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
        slug = re.sub(r"[^a-z0-9]+", "-", normalized_title).strip("-")[:32] or "memory"
        return f"mem-{self.type.value}-{slug}-{digest}"

    def to_json_dict(self) -> dict:
        return {
            "type": self.type.value,
            "scope": self.scope.value,
            "project_id": self.project_id,
            "title": self.title,
            "body": self.body,
            "sources": [{"kind": x.kind, "ref": x.ref} for x in self.sources],
            "evidence_ids": list(self.evidence_ids),
            "related_paths": list(self.related_paths),
            "tags": list(self.tags),
            "sensitivity": self.sensitivity.value,
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> "MemoryDraft":
        return cls(
            type=MemoryType(data["type"]),
            scope=MemoryScope(data["scope"]),
            project_id=data.get("project_id"),
            title=str(data["title"]),
            body=str(data["body"]),
            sources=tuple(
                MemorySource(str(x["kind"]), str(x["ref"]))
                for x in data.get("sources", [])
            ),
            evidence_ids=tuple(map(str, data.get("evidence_ids", []))),
            related_paths=tuple(map(str, data.get("related_paths", []))),
            tags=tuple(map(str, data.get("tags", []))),
            sensitivity=MemorySensitivity(data.get("sensitivity", "INTERNAL")),
        )

    def to_record(self, memory_id: str | None = None) -> "MemoryRecord":
        now = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        return MemoryRecord(
            schema_version=1,
            id=memory_id or self.suggested_id(),
            type=self.type,
            scope=self.scope,
            project_id=self.project_id,
            title=self.title.strip(),
            body=self.body.strip(),
            status=MemoryStatus.CANDIDATE,
            confidence=MemoryConfidence.LOW,
            created_at=now,
            verified_at=None,
            valid_at_commit=None,
            sources=self.sources,
            evidence_ids=self.evidence_ids,
            related_paths=self.related_paths,
            tags=self.tags,
            supersedes=(),
            sensitivity=self.sensitivity,
        )


@dataclass(frozen=True)
class MemoryRecord:
    schema_version: int
    id: str
    type: MemoryType
    scope: MemoryScope
    project_id: str | None
    title: str
    body: str
    status: MemoryStatus
    confidence: MemoryConfidence
    created_at: str
    verified_at: str | None
    valid_at_commit: str | None
    sources: tuple[MemorySource, ...]
    evidence_ids: tuple[str, ...]
    related_paths: tuple[str, ...]
    tags: tuple[str, ...]
    supersedes: tuple[str, ...]
    sensitivity: MemorySensitivity

    def to_json_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "type": self.type.value,
            "scope": self.scope.value,
            "project_id": self.project_id,
            "title": self.title,
            "body": self.body,
            "status": self.status.value,
            "confidence": self.confidence.value,
            "created_at": self.created_at,
            "verified_at": self.verified_at,
            "valid_at_commit": self.valid_at_commit,
            "sources": [
                {"kind": source.kind, "ref": source.ref} for source in self.sources
            ],
            "evidence_ids": list(self.evidence_ids),
            "related_paths": list(self.related_paths),
            "tags": list(self.tags),
            "supersedes": list(self.supersedes),
            "sensitivity": self.sensitivity.value,
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> "MemoryRecord":
        return cls(
            schema_version=int(data["schema_version"]),
            id=str(data["id"]),
            type=MemoryType(data["type"]),
            scope=MemoryScope(data["scope"]),
            project_id=data.get("project_id"),
            title=str(data["title"]),
            body=str(data["body"]),
            status=MemoryStatus(data["status"]),
            confidence=MemoryConfidence(data["confidence"]),
            created_at=str(data["created_at"]),
            verified_at=data.get("verified_at"),
            valid_at_commit=data.get("valid_at_commit"),
            sources=tuple(
                MemorySource(str(x["kind"]), str(x["ref"]))
                for x in data.get("sources", [])
            ),
            evidence_ids=tuple(map(str, data.get("evidence_ids", []))),
            related_paths=tuple(map(str, data.get("related_paths", []))),
            tags=tuple(map(str, data.get("tags", []))),
            supersedes=tuple(map(str, data.get("supersedes", []))),
            sensitivity=MemorySensitivity(data["sensitivity"]),
        )
