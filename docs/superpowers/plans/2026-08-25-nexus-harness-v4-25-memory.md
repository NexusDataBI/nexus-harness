# Nexus Harness v4 — Plan 2.5 Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runtime-neutral, local-first durable engineering memory layer that stores verified project/portfolio knowledge as Markdown+JSON, retrieves it with deterministic local search, produces bounded context capsules, detects stale/contradictory memories, and exposes stable APIs for Plan 3 runtime hooks.

**Architecture:** Plan 2 operational state remains authoritative for active tasks. Plan 2.5 adds durable project memory inside `.nexus/memory/` plus an optional portfolio Markdown vault, with disposable SQLite FTS5 indexes and lexical fallback; Obsidian is an optional UI only. Memory lifecycle is provenance-driven (`CANDIDATE → VERIFIED → STALE/SUPERSEDED`) and never overrides current repo/spec/evidence truth.

**Tech Stack:** Python 3.11+ standard library, JSON, TOML via `tomllib`, Markdown, `sqlite3`/FTS5 when available, Git subprocesses only through narrow helpers already allowed by the Harness.

**Spec:** `docs/superpowers/specs/2026-08-25-nexus-harness-v4-25-memory-architecture.md`

## Global Constraints

- Read the parent v4 spec and the Plan 2.5 memory spec before Task 1.
- Plan 2 must already be integrated locally and freshly verified before this plan begins.
- Python runtime floor remains 3.11.
- Canonical machine policy uses TOML/JSON; do not introduce a YAML parser.
- Markdown+JSON are canonical memory; SQLite indexes/caches are derived and disposable.
- Obsidian is optional UI only; no Obsidian plugin or Sync dependency is introduced.
- Do not install Claude-Mem, Chroma, Qdrant, Pinecone, pgvector or an embedding API.
- Project memory must work when portfolio memory is not configured.
- Retrieval must work when SQLite FTS5 is unavailable.
- Only `VERIFIED` memories are auto-injected into normal context capsules.
- `CANDIDATE`, `SUPERSEDED`, `REJECTED` and `ARCHIVED` are excluded from normal recall.
- `STALE` memories are excluded from normal recall and may appear only as warnings/search results.
- Memory never bypasses Plan 2 Acceptance, Quality, Security, Review or Completion Gates.
- Memory never becomes authority over explicit user instructions, current approved specs, fresh executable evidence or current repo truth.
- Secrets, credentials and raw sensitive customer payloads are invalid memory.
- No absolute user path belongs in committed canonical configuration.
- Runtime-specific Claude/Cursor/Codex wiring is deferred to Plan 3.
- Use standard-library `unittest`.
- Implement behavior test-first where isolatable.
- Every task gets fresh implementer review and scoped re-review before completion.

---

## File Structure

### Canonical policy/schema

- `core/memory/memory-record.schema.json` — machine schema for memory sidecars.
- `core/memory/memory-policy.toml` — lifecycle, sensitivity, candidate/promotion and budget policy.
- `core/memory/retrieval-policy.toml` — deterministic ranking and capsule budgets.

### Runtime-neutral implementation

- `src/nexus_harness/memory/__init__.py` — public API exports only.
- `src/nexus_harness/memory/models.py` — enums/dataclasses and JSON serialization.
- `src/nexus_harness/memory/store.py` — canonical file layout, atomic read/write and project initialization.
- `src/nexus_harness/memory/guard.py` — persistence boundary validation/redaction rejection.
- `src/nexus_harness/memory/freshness.py` — Git/path freshness and contradiction primitives.
- `src/nexus_harness/memory/retrieval.py` — filesystem retrieval, SQLite FTS5 derived index and lexical fallback.
- `src/nexus_harness/memory/capsule.py` — HOT/WARM bounded context capsule rendering.
- `src/nexus_harness/memory/lifecycle.py` — candidate collection, promotion, supersession and portfolio-promotion rules.
- `src/nexus_harness/memory/portfolio.py` — vault initialization and project bridge records.
- `src/nexus_harness/memory/doctor.py` — integrity/health checks.

### Templates/commands

- `templates/memory/project-memory/README.md`
- `templates/memory/portfolio-vault/HOME.md`
- `templates/memory/portfolio-vault/VAULT_RULES.md`
- `templates/memory/portfolio-vault/RETRIEVAL_PROTOCOL.md`
- `scripts/memory`

### Tests

- `tests/test_memory_models.py`
- `tests/test_memory_store.py`
- `tests/test_memory_guard.py`
- `tests/test_memory_freshness.py`
- `tests/test_memory_retrieval.py`
- `tests/test_memory_capsule.py`
- `tests/test_memory_lifecycle.py`
- `tests/test_memory_portfolio.py`
- `tests/test_memory_doctor.py`
- `tests/test_memory_integration.py`

---

### Task 1: Define memory records, schemas and policy

**Files:**
- Create: `core/memory/memory-record.schema.json`
- Create: `core/memory/memory-policy.toml`
- Create: `core/memory/retrieval-policy.toml`
- Create: `src/nexus_harness/memory/__init__.py`
- Create: `src/nexus_harness/memory/models.py`
- Create: `tests/test_memory_models.py`

**Interfaces:**
- Consumes: Plan 2 `TaskState`/evidence concepts only by identifier; no import from runtime adapters.
- Produces: `MemoryStatus`, `MemoryType`, `MemoryScope`, `MemorySensitivity`, `MemorySource`, `MemoryRecord`, `MemoryDraft`, deterministic JSON serialization.

- [ ] **Step 1: Write the failing model-default tests**

Create `tests/test_memory_models.py`:

```python
import unittest
from nexus_harness.memory.models import (
    MemoryDraft,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)

class MemoryModelTests(unittest.TestCase):
    def test_new_draft_is_candidate(self):
        draft = MemoryDraft(
            type=MemoryType.LESSON,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Use isolated DB ports",
            body="Integration tests must allocate isolated DB ports.",
        )
        record = draft.to_record(memory_id="mem-lesson-db-ports-a1b2c3d4")
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)

    def test_memory_id_is_stable_for_same_identity(self):
        a = MemoryDraft(
            type=MemoryType.INVARIANT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Backward compatible migrations",
            body="body one",
        )
        b = MemoryDraft(
            type=MemoryType.INVARIANT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Backward compatible migrations",
            body="body two",
        )
        self.assertEqual(a.suggested_id(), b.suggested_id())
```

- [ ] **Step 2: Run the model tests and confirm RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_models -v
```

Expected: import failure because the memory package does not exist.

- [ ] **Step 3: Implement exact enums and source model**

Create `src/nexus_harness/memory/models.py` with these public enums:

```python
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
```

Add immutable `MemorySource(kind: str, ref: str)`.

- [ ] **Step 4: Implement `MemoryDraft` and `MemoryRecord`**

The models must expose these exact fields:

```python
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
        identity = "\n".join((
            self.scope.value,
            self.project_id or "",
            self.type.value,
            normalized_title,
        ))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
        slug = re.sub(r"[^a-z0-9]+", "-", normalized_title).strip("-")[:32] or "memory"
        return f"mem-{self.type.value}-{slug}-{digest}"

    def to_json_dict(self) -> dict:
        return {
            "type": self.type.value, "scope": self.scope.value, "project_id": self.project_id,
            "title": self.title, "body": self.body,
            "sources": [{"kind": x.kind, "ref": x.ref} for x in self.sources],
            "evidence_ids": list(self.evidence_ids), "related_paths": list(self.related_paths),
            "tags": list(self.tags), "sensitivity": self.sensitivity.value,
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> "MemoryDraft":
        return cls(
            type=MemoryType(data["type"]), scope=MemoryScope(data["scope"]),
            project_id=data.get("project_id"), title=str(data["title"]), body=str(data["body"]),
            sources=tuple(MemorySource(str(x["kind"]), str(x["ref"])) for x in data.get("sources", [])),
            evidence_ids=tuple(map(str, data.get("evidence_ids", []))),
            related_paths=tuple(map(str, data.get("related_paths", []))),
            tags=tuple(map(str, data.get("tags", []))),
            sensitivity=MemorySensitivity(data.get("sensitivity", "INTERNAL")),
        )

    def to_record(self, memory_id: str | None = None) -> "MemoryRecord":
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
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
            "sources": [{"kind": s.kind, "ref": s.ref} for s in self.sources],
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
            sources=tuple(MemorySource(str(x["kind"]), str(x["ref"])) for x in data.get("sources", [])),
            evidence_ids=tuple(map(str, data.get("evidence_ids", []))),
            related_paths=tuple(map(str, data.get("related_paths", []))),
            tags=tuple(map(str, data.get("tags", []))),
            supersedes=tuple(map(str, data.get("supersedes", []))),
            sensitivity=MemorySensitivity(data["sensitivity"]),
        )
```

`MemoryDraft.suggested_id()` must use SHA-256 over canonical UTF-8 text:

```text
<scope>\n<project-id-or-empty>\n<type>\n<normalized-lowercase-title>
```

ID format:

```text
mem-<type>-<slug-up-to-32-chars>-<first-8-sha256-hex>
```

Use only standard library.

- [ ] **Step 5: Create canonical JSON schema**

Create `core/memory/memory-record.schema.json` as JSON Schema Draft 2020-12. Require every field listed in `MemoryRecord`; enum values must exactly match the Python enums. Require `schema_version` equal `1`. `id` must match `^mem-[a-z]+-[a-z0-9-]+-[0-9a-f]{8}$`.

- [ ] **Step 6: Create memory policy**

Create `core/memory/memory-policy.toml` with exact baseline:

```toml
schema_version = 1

auto_inject_statuses = ["VERIFIED"]
stale_warning_enabled = true
candidate_auto_inject = false
confidential_auto_inject = false

[promotion]
decision_sources = ["approved_spec", "adr", "explicit_user_decision", "accepted_issue_or_pr_decision"]
invariant_sources = ["approved_spec", "policy", "deterministic_evidence", "adr"]
component_sources = ["canonical_doc", "deterministic_evidence"]
lesson_sources = ["bug_card", "incident", "review_finding"]
incident_sources = ["incident", "github_issue"]
pattern_min_independent_sources = 2

[storage]
project_relative_path = ".nexus/memory"
atomic_pair_writes = true
```

- [ ] **Step 7: Create retrieval policy**

Create `core/memory/retrieval-policy.toml`:

```toml
schema_version = 1

[weights]
same_project = 20
exact_path = 16
path_prefix = 10
exact_tag = 8
exact_tag_cap = 24
title_token = 5
title_token_cap = 20
body_token = 2
body_token_cap = 20
requested_type = 10
verified_fresh = 12
verified_unknown = 4
stale = -30

[capsule]
hot_max_chars = 6000
warm_max_chars = 10000
max_items = 16
max_item_chars = 1800
include_stale_warnings = true
```

- [ ] **Step 8: Export the public model API**

Create `src/nexus_harness/memory/__init__.py` exporting only the stable types/functions introduced by completed tasks. At this task export the enums/models only.

- [ ] **Step 9: Run Task 1 tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_models -v
```

Expected: PASS.

- [ ] **Step 10: Run schema/config validation**

Run:

```bash
scripts/validate
```

Expected: exit 0. If Plan 1 validator does not yet know `core/memory`, it still must reject absolute paths/secrets/model leakage there through the global canonical scan.

- [ ] **Step 11: Commit Task 1**

```bash
git add core/memory src/nexus_harness/memory tests/test_memory_models.py
git commit -m "feat: define nexus durable memory records"
```

---

### Task 2: Implement canonical project storage and memory guard

**Files:**
- Create: `src/nexus_harness/memory/store.py`
- Create: `src/nexus_harness/memory/guard.py`
- Create: `templates/memory/project-memory/README.md`
- Create: `tests/test_memory_store.py`
- Create: `tests/test_memory_guard.py`

**Interfaces:**
- Consumes: `MemoryRecord`, `MemoryDraft`, memory policy.
- Produces: `init_project_memory()`, `write_memory()`, `read_memory()`, `load_project_memories()`, atomic Markdown/JSON pair handling, `MemoryGuardError`.

- [ ] **Step 1: Write failing project-store roundtrip test**

Create `tests/test_memory_store.py`:

```python
import tempfile
import unittest
from pathlib import Path
from nexus_harness.memory.models import MemoryDraft, MemoryScope, MemoryType
from nexus_harness.memory.store import init_project_memory, write_memory, read_memory

class MemoryStoreTests(unittest.TestCase):
    def test_write_creates_markdown_and_json_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            draft = MemoryDraft(
                type=MemoryType.COMPONENT,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="API owns lead state",
                body="The API is authoritative for persisted lead state.",
            )
            record = write_memory(root, draft.to_record())
            category = root / ".nexus" / "memory" / "components"
            self.assertTrue((category / f"{record.id}.md").exists())
            self.assertTrue((category / f"{record.id}.json").exists())
            self.assertEqual(read_memory(root, record.id), record)
```

- [ ] **Step 2: Write failing secret-boundary test**

Create `tests/test_memory_guard.py`:

```python
import unittest
from nexus_harness.memory.guard import MemoryGuardError, validate_memory_text

class MemoryGuardTests(unittest.TestCase):
    def test_rejects_private_key_material(self):
        with self.assertRaises(MemoryGuardError):
            validate_memory_text("-----BEGIN OPENSSH PRIVATE KEY----- secret")

    def test_rejects_env_secret_assignment(self):
        with self.assertRaises(MemoryGuardError):
            validate_memory_text("DATABASE_PASSWORD=super-secret-value")
```

- [ ] **Step 3: Confirm RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_store tests.test_memory_guard -v
```

Expected: import failure.

- [ ] **Step 4: Implement category mapping and project initialization**

`store.py` must map types exactly:

```python
CATEGORY_BY_TYPE = {
    MemoryType.DECISION: "decisions",
    MemoryType.INVARIANT: "invariants",
    MemoryType.COMPONENT: "components",
    MemoryType.PATTERN: "patterns",
    MemoryType.LESSON: "lessons",
    MemoryType.INCIDENT: "incidents",
}
```

`init_project_memory(project_root: Path) -> Path` creates `.nexus/memory/`, all category dirs and deterministic `README.md`; it must be idempotent and never delete unknown user files.

- [ ] **Step 5: Implement guard rules**

`guard.py` exposes:

```python
class MemoryGuardError(ValueError):
    """Raised when content violates the durable-memory persistence boundary."""

SECRET_RULES = (
    ("private_key", re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----", re.I)),
    ("github_token", re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{16,}\b")),
    ("api_token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("bearer", re.compile(r"Authorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{12,}", re.I)),
    ("secret_assignment", re.compile(r"(?im)^\s*[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)[A-Z0-9_]*\s*=\s*\S+")),
)

def validate_memory_text(text: str) -> None:
    for rule_name, pattern in SECRET_RULES:
        if pattern.search(text):
            raise MemoryGuardError(f"memory rejected by guard rule: {rule_name}")

def validate_memory_record(record: MemoryRecord) -> None:
    validate_memory_text(record.title)
    validate_memory_text(record.body)
    for source in record.sources:
        validate_memory_text(source.ref)
```

Reject at minimum:

- PEM/private key headers;
- common token prefixes (`ghp_`, `github_pat_`, `sk-` followed by long token material);
- assignments whose key contains `PASSWORD`, `SECRET`, `TOKEN`, `API_KEY`, `PRIVATE_KEY` and whose value is non-empty;
- obvious bearer credentials (`Authorization: Bearer ...`).

Do not log the matched secret value. Exceptions report only the rule name.

- [ ] **Step 6: Implement atomic paired write**

`write_memory(project_root: Path, record: MemoryRecord, *, replace: bool = False) -> MemoryRecord` must:

1. call guard validation;
2. reject duplicate ID when existing content differs and `replace=False`; when `replace=True`, require the existing record to have the same `id`, `type`, `scope` and `project_id` so lifecycle updates cannot silently move identity/category;
3. render Markdown from `record.title` and `record.body` with a final `## Nexus Memory` section listing ID/status/type/sources as human pointers but no duplicate JSON dump;
4. write `.md.tmp` and `.json.tmp` in the target category;
5. flush/fsync where available;
6. `os.replace()` JSON then Markdown only after both temp writes succeed;
7. clean temps on failure;
8. doctor later detects impossible partial pairs.

- [ ] **Step 7: Implement read/load**

Expose:

Implement these exact signatures:

```python
def read_memory(project_root: Path, memory_id: str) -> MemoryRecord:
    matches = [p for p in _sidecar_paths(project_root) if p.stem == memory_id]
    if len(matches) != 1:
        raise MemoryStoreError(f"expected exactly one sidecar for {memory_id}; found {len(matches)}")
    data = json.loads(matches[0].read_text(encoding="utf-8"))
    return MemoryRecord.from_json_dict(data)

def load_project_memories(project_root: Path) -> list[MemoryRecord]:
    records = [MemoryRecord.from_json_dict(json.loads(p.read_text(encoding="utf-8"))) for p in _sidecar_paths(project_root)]
    ids = [r.id for r in records]
    if len(ids) != len(set(ids)):
        raise MemoryStoreError("duplicate memory id")
    return sorted(records, key=lambda r: r.id)
```

`_sidecar_paths()` searches category `*.json` files only, ignores `*.tmp`, and returns deterministic path order.

- [ ] **Step 8: Add atomic failure regression test**

Patch the second temporary-file write to raise `OSError`; prove no canonical `.md` or `.json` pair is published for the new memory ID.

- [ ] **Step 9: Run Task 2 tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_store tests.test_memory_guard -v
```

Expected: PASS.

- [ ] **Step 10: Commit Task 2**

```bash
git add src/nexus_harness/memory/store.py src/nexus_harness/memory/guard.py templates/memory/project-memory tests/test_memory_store.py tests/test_memory_guard.py
git commit -m "feat: persist guarded project memory"
```

---

### Task 3: Implement provenance freshness and contradiction resolution

**Files:**
- Create: `src/nexus_harness/memory/freshness.py`
- Create: `tests/test_memory_freshness.py`

**Interfaces:**
- Consumes: `MemoryRecord`, repo root/current commit and related paths.
- Produces: `FreshnessStatus`, `FreshnessResult`, `compute_memory_freshness()`, `resolve_contradiction()`.

- [ ] **Step 1: Write failing stale-path test**

Create `tests/test_memory_freshness.py`:

```python
import tempfile
import unittest
from pathlib import Path
from nexus_harness.memory.freshness import FreshnessStatus, compute_memory_freshness
from nexus_harness.memory.models import (
    MemoryConfidence, MemoryRecord, MemoryScope, MemorySensitivity,
    MemoryStatus, MemoryType,
)

class MemoryFreshnessTests(unittest.TestCase):
    def record(self, commit):
        return MemoryRecord(
            schema_version=1,
            id="mem-component-auth-a1b2c3d4",
            type=MemoryType.COMPONENT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Auth entrypoint",
            body="Auth lives in src/auth.py",
            status=MemoryStatus.VERIFIED,
            confidence=MemoryConfidence.HIGH,
            created_at="2026-08-25T00:00:00Z",
            verified_at="2026-08-25T00:00:00Z",
            valid_at_commit=commit,
            sources=(), evidence_ids=(),
            related_paths=("src/auth.py",), tags=("auth",), supersedes=(),
            sensitivity=MemorySensitivity.INTERNAL,
        )

    def test_changed_related_path_is_stale(self):
        # Test helper creates a temporary git repository with commit A,
        # modifies src/auth.py, commits B and evaluates record valid at A.
        from tests.memory_git_helper import make_repo_with_changed_file
        root, base_commit = make_repo_with_changed_file("src/auth.py")
        result = compute_memory_freshness(root, self.record(base_commit))
        self.assertEqual(result.status, FreshnessStatus.STALE)
```

Create `tests/memory_git_helper.py` in the same Task with a helper that initializes a temporary Git repository, configures local test identity, commits an initial file, changes that file, commits again and returns `(Path, base_sha)`; use `subprocess.run(..., check=True, capture_output=True, text=True)` and no shell.

- [ ] **Step 2: Confirm RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_freshness -v
```

Expected: import failure.

- [ ] **Step 3: Implement freshness statuses**

`freshness.py` defines:

```python
class FreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True)
class FreshnessResult:
    status: FreshnessStatus
    reasons: tuple[str, ...]
    changed_paths: tuple[str, ...] = ()
```

- [ ] **Step 4: Implement Git/path freshness**

`compute_memory_freshness(repo_root, record)` rules:

- non-VERIFIED memory returns `UNKNOWN` with reason `status_not_verified`;
- missing `valid_at_commit` returns `UNKNOWN`;
- no `related_paths` returns `UNKNOWN` unless a source-specific future policy says otherwise;
- unknown/unreachable commit returns `UNKNOWN`, never crashes recall;
- use `git diff --name-only <valid_at_commit>..HEAD --` to obtain changed paths;
- compare each changed path to exact/glob-like related path patterns using `PurePosixPath.match` plus prefix semantics for patterns ending `/**`;
- overlap returns `STALE` with changed paths;
- no overlap returns `FRESH`.

Do not execute arbitrary shell text.

- [ ] **Step 5: Implement contradiction resolution primitive**

Expose:

```python
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
class ContradictionResolution:
    winner: str | None
    excluded: tuple[str, ...]
    requires_adjudication: bool
    reason: str
```

`resolve_contradiction(items: list[tuple[str, TruthStrength]])` selects a unique strongest item. Ties at the strongest level return `requires_adjudication=True` and no winner.

- [ ] **Step 6: Add precedence tests**

Test:

- `CURRENT_REPO` beats `VERIFIED_PROJECT_MEMORY`;
- equal-strength conflicting project memories require adjudication;
- stale memory never beats verified memory.

- [ ] **Step 7: Run Task 3 tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_freshness -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

```bash
git add src/nexus_harness/memory/freshness.py tests/test_memory_freshness.py tests/memory_git_helper.py
git commit -m "feat: invalidate stale engineering memory"
```

---

### Task 4: Implement deterministic retrieval, disposable FTS index and fallback

**Files:**
- Create: `src/nexus_harness/memory/retrieval.py`
- Create: `tests/test_memory_retrieval.py`

**Interfaces:**
- Consumes: canonical memory records, freshness results and retrieval policy.
- Produces: `MemoryQueryContext`, `MemoryHit`, `search_memory()`, `rebuild_index()`.

- [ ] **Step 1: Write failing relevance/fallback tests**

Create `tests/test_memory_retrieval.py` with these behaviors:

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nexus_harness.memory.models import MemoryDraft, MemoryScope, MemoryType
from nexus_harness.memory.retrieval import MemoryQueryContext, search_memory
from nexus_harness.memory.store import init_project_memory, write_memory

class MemoryRetrievalTests(unittest.TestCase):
    def test_matching_path_and_tag_rank_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            first = MemoryDraft(
                type=MemoryType.INVARIANT, scope=MemoryScope.PROJECT,
                project_id="repo-1", title="Auth token rotation",
                body="Rotate auth credentials without invalidating active migration jobs.",
                related_paths=("src/auth/**",), tags=("auth",),
            ).to_record()
            second = MemoryDraft(
                type=MemoryType.LESSON, scope=MemoryScope.PROJECT,
                project_id="repo-1", title="CSS layout lesson",
                body="Prefer grid for this dashboard.", tags=("frontend",),
            ).to_record()
            # Tests may promote fixtures through the lifecycle helper once Task 5 exists;
            # for Task 4 use dataclasses.replace to mark test fixtures VERIFIED.
            from dataclasses import replace
            from nexus_harness.memory.models import MemoryConfidence, MemoryStatus
            first = replace(first, status=MemoryStatus.VERIFIED, confidence=MemoryConfidence.HIGH)
            second = replace(second, status=MemoryStatus.VERIFIED, confidence=MemoryConfidence.HIGH)
            write_memory(root, first); write_memory(root, second)
            hits = search_memory(root, "auth rotation", MemoryQueryContext(
                project_id="repo-1", affected_paths=("src/auth/session.py",), tags=("auth",)
            ))
            self.assertEqual(hits[0].record.id, first.id)

    @patch("nexus_harness.memory.retrieval.fts5_available", return_value=False)
    def test_lexical_fallback_works_without_fts5(self, _):
        from dataclasses import replace
        from nexus_harness.memory.models import MemoryConfidence, MemoryStatus
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            record = MemoryDraft(
                type=MemoryType.LESSON, scope=MemoryScope.PROJECT,
                project_id="repo-1", title="Retry idempotency",
                body="Webhook retries require stable idempotency keys.",
                tags=("webhook", "idempotency"),
            ).to_record()
            record = replace(record, status=MemoryStatus.VERIFIED, confidence=MemoryConfidence.HIGH)
            write_memory(root, record)
            hits = search_memory(root, "webhook idempotency", MemoryQueryContext(project_id="repo-1"))
            self.assertGreaterEqual(len(hits), 1)
            self.assertEqual(hits[0].record.id, record.id)
```

- [ ] **Step 2: Confirm RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_retrieval -v
```

Expected: import failure.

- [ ] **Step 3: Implement query/hit types**

```python
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
```

- [ ] **Step 4: Implement deterministic tokenization/scoring**

Tokenization:

```python
def tokenize(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(re.findall(r"[a-z0-9_]{2,}", text.lower()))))
```

Implement exact weights from `core/memory/retrieval-policy.toml`. Candidate/superseded/rejected/archived records are excluded. Stale is excluded unless `include_stale=True`. Confidential records are excluded from baseline auto-search unless an explicit future permission flag is added; do not add that flag in this task.

- [ ] **Step 5: Implement cache location and FTS5 capability check**

Derived index location function:

```python
def default_index_path(repo_id: str, cache_home: Path | None = None) -> Path:
    base = cache_home or Path.home() / ".nexus-harness" / "memory-cache"
    return base / repo_id / "memory.db"
```

This path exists only at runtime and is never emitted to committed canonical config.

`fts5_available(connection=None) -> bool` creates a temporary in-memory virtual table and returns False on `sqlite3.OperationalError`.

- [ ] **Step 6: Implement rebuildable index**

`rebuild_index(records, db_path)` creates/replaces derived tables. Store memory ID, project ID, type, title, body and tags. The canonical JSON/Markdown files remain the source of truth.

If rebuild fails, `search_memory()` must fall back to filesystem lexical scoring instead of failing the task.

- [ ] **Step 7: Implement search behavior**

`search_memory(project_root, query, context, *, portfolio_root=None, cache_home=None) -> list[MemoryHit]`:

1. load canonical project records;
2. optionally load portfolio records through `portfolio.py` only when a path is supplied;
3. compute candidate text matches via FTS5 or lexical fallback;
4. compute freshness for project memories when repository context exists;
5. score using policy;
6. stable sort by `(-score, -provenance_strength, verified_at_desc, id)`; if verified time parsing is inconvenient, normalize to sortable ISO 8601 strings;
7. return maximum 50 raw hits; capsule task applies stricter item budgets.

- [ ] **Step 8: Add disposable-index test**

Build the index, delete `memory.db`, search again and prove the same top memory ID is returned.

- [ ] **Step 9: Run Task 4 tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_retrieval -v
```

Expected: PASS.

- [ ] **Step 10: Commit Task 4**

```bash
git add src/nexus_harness/memory/retrieval.py tests/test_memory_retrieval.py
git commit -m "feat: retrieve memory without vector services"
```

---

### Task 5: Implement memory lifecycle, promotion and Plan 2 candidate capture

**Files:**
- Create: `src/nexus_harness/memory/lifecycle.py`
- Create: `tests/test_memory_lifecycle.py`

**Interfaces:**
- Consumes: Plan 2 `TaskState`, `Evidence`/confirmed findings through narrow data inputs, memory policy.
- Produces: `collect_memory_candidates()`, `verify_memory()`, `supersede_memory()`, `promote_to_portfolio_draft()`.

- [ ] **Step 1: Write failing promotion tests**

Create `tests/test_memory_lifecycle.py`:

```python
import unittest
from nexus_harness.memory.lifecycle import MemoryPromotionError, verify_record
from nexus_harness.memory.models import (
    MemoryDraft, MemoryScope, MemorySource, MemoryStatus, MemoryType,
)

class MemoryLifecycleTests(unittest.TestCase):
    def test_decision_without_authoritative_source_stays_candidate(self):
        record = MemoryDraft(
            type=MemoryType.DECISION,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Use queue X",
            body="Queue X is the selected transport.",
        ).to_record()
        with self.assertRaises(MemoryPromotionError):
            verify_record(record, current_commit="abc")

    def test_decision_with_adr_can_verify(self):
        record = MemoryDraft(
            type=MemoryType.DECISION,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Use queue X",
            body="Queue X is the selected transport.",
            sources=(MemorySource("adr", "ADR-001"),),
        ).to_record()
        verified = verify_record(record, current_commit="abc")
        self.assertEqual(verified.status, MemoryStatus.VERIFIED)
        self.assertEqual(verified.valid_at_commit, "abc")
```

- [ ] **Step 2: Confirm RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_lifecycle -v
```

Expected: import failure.

- [ ] **Step 3: Implement type-specific promotion rules**

`verify_record(record, current_commit, evidence_lookup=None) -> MemoryRecord`:

- require `record.status == CANDIDATE` or `STALE`;
- validate allowed source kinds from `memory-policy.toml`;
- pattern requires at least two distinct source refs unless an `approved_spec`/`adr` source exists;
- deterministic-evidence sources require the referenced ID to be present and, when an `evidence_lookup` callable is supplied, exit code must be 0 and evidence diff must match current diff passed by the caller;
- set `status=VERIFIED`, `confidence=HIGH`, `verified_at=UTC now`, `valid_at_commit=current_commit`;
- never mutate the original frozen record.

- [ ] **Step 4: Implement candidate collection with explicit allowlist**

Expose:

```python
@dataclass(frozen=True)
class CandidateSignal:
    kind: str
    title: str
    statement: str
    sources: tuple[MemorySource, ...]
    evidence_ids: tuple[str, ...] = ()
    related_paths: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


def collect_memory_candidates(
    *,
    project_id: str,
    task_id: str,
    signals: tuple[CandidateSignal, ...],
) -> list[MemoryDraft]:
    mapping = {
        "architecture_decision": MemoryType.DECISION,
        "invariant": MemoryType.INVARIANT,
        "component_fact": MemoryType.COMPONENT,
        "reusable_pattern": MemoryType.PATTERN,
        "confirmed_bug_lesson": MemoryType.LESSON,
        "confirmed_incident": MemoryType.INCIDENT,
    }
    drafts = []
    for signal in signals:
        memory_type = mapping.get(signal.kind)
        if memory_type is None:
            continue
        drafts.append(MemoryDraft(
            type=memory_type,
            scope=MemoryScope.PROJECT,
            project_id=project_id,
            title=signal.title,
            body=signal.statement,
            sources=signal.sources,
            evidence_ids=signal.evidence_ids,
            related_paths=signal.related_paths,
            tags=signal.tags,
        ))
    return drafts
```

Only these signal kinds map to memory types:

```text
architecture_decision → decision
invariant → invariant
component_fact → component
reusable_pattern → pattern
confirmed_bug_lesson → lesson
confirmed_incident → incident
```

Unknown/transient signal kinds are ignored and returned separately only through a structured count if needed; do not serialize full task state or tool transcript.


- [ ] **Step 4A: Implement stored lifecycle updates**

Expose:

```python
def verify_memory(project_root, memory_id, *, current_commit, evidence_lookup=None):
    record = read_memory(Path(project_root), memory_id)
    verified = verify_record(record, current_commit=current_commit, evidence_lookup=evidence_lookup)
    return write_memory(Path(project_root), verified, replace=True)

def supersede_memory(project_root, old_memory_id, replacement_memory_id):
    old = read_memory(Path(project_root), old_memory_id)
    updated = supersede_record(old, replacement_memory_id)
    return write_memory(Path(project_root), updated, replace=True)
```

These are the mutation paths used by the CLI. Do not let callers update `status` by editing JSON directly through a public API.

- [ ] **Step 5: Add raw-transcript rejection test**

Pass a signal kind `tool_call` with body containing a command and prove `collect_memory_candidates()` returns no draft for it.

- [ ] **Step 6: Implement supersession**

`supersede_record(old, new_id) -> MemoryRecord` sets old status to `SUPERSEDED`; the replacement record may list old ID in `supersedes`. Reject self-supersession.

- [ ] **Step 7: Implement portfolio-promotion draft**

`promote_to_portfolio_draft(records, title, body, tags) -> MemoryDraft` requires at least one `VERIFIED` project source record; create `MemorySource(kind="project_memory", ref=<id>)` for each contributing record. Scope is `PORTFOLIO`, `project_id=None`, status remains candidate until its promotion rule is satisfied.

- [ ] **Step 8: Run Task 5 tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_lifecycle -v
```

Expected: PASS.

- [ ] **Step 9: Commit Task 5**

```bash
git add src/nexus_harness/memory/lifecycle.py tests/test_memory_lifecycle.py
git commit -m "feat: promote only verified durable memory"
```

---

### Task 6: Build bounded context capsules

**Files:**
- Create: `src/nexus_harness/memory/capsule.py`
- Create: `tests/test_memory_capsule.py`

**Interfaces:**
- Consumes: ranked `MemoryHit`s, task/project context and retrieval policy.
- Produces: `ContextCapsule` with deterministic HOT/WARM sections and stale warnings.

- [ ] **Step 1: Write failing capsule-budget tests**

Create `tests/test_memory_capsule.py` with fixtures that construct verified `MemoryHit`s and assert:

```python
capsule = build_context_capsule(
    project_id="repo-1",
    diff_hash="abc",
    hits=hits,
    hot_memory_ids=(hits[0].record.id,),
    policy=CapsulePolicy(hot_max_chars=500, warm_max_chars=800, max_items=3, max_item_chars=300),
)
self.assertLessEqual(len(capsule.hot), 500)
self.assertLessEqual(len(capsule.warm), 800)
self.assertLessEqual(capsule.item_count, 3)
self.assertIn(hits[0].record.id, capsule.text)
```

Add a stale hit and prove it appears only in `STALE/CONFLICT WARNINGS`, not HOT/WARM.

- [ ] **Step 2: Confirm RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_capsule -v
```

Expected: import failure.

- [ ] **Step 3: Implement capsule types**

```python
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

    @property
    def text(self) -> str:
        parts = [f"NEXUS CONTEXT CAPSULE\nProject: {self.project_id or 'unknown'}\nDiff: {self.diff_hash or 'unknown'}"]
        if self.hot:
            parts.append("HOT\n" + self.hot)
        if self.warm:
            parts.append("WARM\n" + self.warm)
        if self.warnings:
            parts.append("STALE/CONFLICT WARNINGS\n" + self.warnings)
        return "\n\n".join(parts).rstrip() + "\n"
```

- [ ] **Step 4: Implement item rendering**

Each included memory renders:

```text
- [<TYPE>] <title>
  <body excerpt>
  source: <memory-id> | freshness: <status>
```

Use body text clipped to `max_item_chars` at a whitespace boundary, adding `…`. Never remove the source/freshness line from an included item.

- [ ] **Step 5: Implement HOT/WARM selection**

- explicit `hot_memory_ids` are considered first if record is VERIFIED and not stale/confidential;
- remaining ranked verified/fresh hits go WARM;
- enforce total `max_items` and per-section char limits at item boundaries;
- stale hits become warnings when policy allows;
- candidate/confidential/superseded/rejected/archived never enter the capsule.

- [ ] **Step 6: Add deterministic-order test**

Same inputs in different list order must produce byte-identical capsule output after ranking metadata is identical.

- [ ] **Step 7: Run Task 6 tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_capsule -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add src/nexus_harness/memory/capsule.py tests/test_memory_capsule.py
git commit -m "feat: build bounded nexus context capsules"
```

---

### Task 7: Implement optional portfolio vault and Obsidian-compatible bridge

**Files:**
- Create: `src/nexus_harness/memory/portfolio.py`
- Create: `templates/memory/portfolio-vault/HOME.md`
- Create: `templates/memory/portfolio-vault/VAULT_RULES.md`
- Create: `templates/memory/portfolio-vault/RETRIEVAL_PROTOCOL.md`
- Create: `tests/test_memory_portfolio.py`

**Interfaces:**
- Consumes: project memory APIs and an explicit target directory.
- Produces: ordinary Markdown/JSON portfolio vault and generated project bridge cards; no Obsidian dependency.

- [ ] **Step 1: Write failing vault-init test**

Create `tests/test_memory_portfolio.py`:

```python
import tempfile
import unittest
from pathlib import Path
from nexus_harness.memory.portfolio import init_portfolio_vault

class PortfolioMemoryTests(unittest.TestCase):
    def test_vault_is_plain_files_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "NexusMemory"
            init_portfolio_vault(root)
            init_portfolio_vault(root)
            self.assertTrue((root / "HOME.md").exists())
            self.assertTrue((root / "VAULT_RULES.md").exists())
            self.assertTrue((root / "projects").is_dir())
            self.assertFalse((root / ".obsidian" / "plugins").exists())
```

- [ ] **Step 2: Confirm RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_portfolio -v
```

Expected: import failure.

- [ ] **Step 3: Create template content**

`VAULT_RULES.md` must state:

- repository/current evidence beats vault memory;
- do not store secrets;
- only verified memory is normal recall;
- project facts remain project-scoped;
- bridge cards are pointers, not duplicated project wikis;
- derived indexes are disposable.

`RETRIEVAL_PROTOCOL.md` must document HOT → WARM → COLD progressive disclosure and stop retrieval once sufficient context exists.

`HOME.md` must link Projects, Domains, Patterns, Lessons, Decisions and Incidents.

- [ ] **Step 4: Implement vault initializer**

`init_portfolio_vault(target_dir: Path) -> Path`:

- rejects target if it is a file;
- creates dirs: `projects`, `domains`, `patterns`, `lessons`, `decisions`, `incidents`, `.nexus-memory/cache`;
- copies baseline templates only when missing;
- never deletes or overwrites user-edited existing Markdown;
- does not create a Git remote;
- does not install Obsidian or plugins.

- [ ] **Step 4A: Implement portfolio memory loading**

Portfolio durable records use the same `<id>.md` + `<id>.json` pair format inside the vault's `patterns/`, `lessons/`, `decisions/` and `incidents/` directories. Add `load_portfolio_memories(vault_root: Path) -> list[MemoryRecord]` that reads only `scope=PORTFOLIO`, rejects duplicate IDs and returns stable ID order. Project-specific `components` and `invariants` are not promoted to new portfolio categories; reusable consequences become portfolio patterns/lessons/decisions/incidents.

- [ ] **Step 5: Implement project bridge rendering**

Expose:

```python
@dataclass(frozen=True)
class ProjectBridge:
    project_id: str
    repository: str
    canonical_memory_path: str
    status: str | None = None
    current_focus: str | None = None
    related_memory_ids: tuple[str, ...] = ()


def write_project_bridge(vault_root: Path, bridge: ProjectBridge) -> Path:
    path = vault_root / "projects" / f"{bridge.project_id}.md"
    start = "<!-- NEXUS:GENERATED:START -->"
    end = "<!-- NEXUS:GENERATED:END -->"
    generated = "\n".join((
        start,
        f"# {bridge.project_id}",
        f"Repository: {bridge.repository}",
        f"Canonical memory: {bridge.canonical_memory_path}",
        f"Status: {bridge.status or 'unknown'}",
        f"Current focus: {bridge.current_focus or 'not set'}",
        "Related memory: " + (", ".join(bridge.related_memory_ids) or "none"),
        end,
    ))
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if start in existing and end in existing:
        prefix, rest = existing.split(start, 1)
        _, suffix = rest.split(end, 1)
        content = prefix.rstrip() + "\n" + generated + suffix
    else:
        content = generated + ("\n\n" + existing.lstrip() if existing else "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
```

The file is `projects/<project-id>.md`. The generated block uses the exact start/end markers shown in the function; content outside those markers is user-owned and preserved.

A future update replaces only that section and preserves user notes outside it.

- [ ] **Step 6: Add bridge-preservation test**

Write bridge, append a manual `## Notes` section, update bridge focus, assert manual notes survive and generated section updates once.

- [ ] **Step 7: Add no-portfolio degradation test**

Call higher-level retrieval with `portfolio_root=None` and prove project retrieval remains PASS with no exception.

- [ ] **Step 8: Run Task 7 tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_portfolio -v
```

Expected: PASS.

- [ ] **Step 9: Commit Task 7**

```bash
git add src/nexus_harness/memory/portfolio.py templates/memory/portfolio-vault tests/test_memory_portfolio.py
git commit -m "feat: add optional portfolio memory vault"
```

---

### Task 8: Add memory doctor, CLI and Plan 3 integration proof

**Files:**
- Create: `src/nexus_harness/memory/doctor.py`
- Create: `src/nexus_harness/memory/cli.py`
- Create: `scripts/memory`
- Create: `tests/test_memory_doctor.py`
- Create: `tests/test_memory_integration.py`
- Modify: `src/nexus_harness/memory/__init__.py`
- Modify: `docs/superpowers/plans/nexus-harness-v4-master-roadmap.md`
- Modify: `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`
- Modify: `docs/memory/PLAN-3-MEMORY-INTEGRATION.md`

**Interfaces:**
- Consumes: all Plan 2.5 modules plus Plan 2 state/evidence types where available.
- Produces: health report, user-facing local command, stable Plan 3 memory API, roadmap insertion between Plan 2 and Plan 3.

- [ ] **Step 1: Write failing doctor tests**

Create `tests/test_memory_doctor.py` proving:

- clean initialized memory returns `PASS`;
- orphan `.md` without `.json` returns `FAIL` finding `orphan_markdown`;
- duplicate memory ID returns `FAIL` finding `duplicate_id`;
- VERIFIED sidecar with no provenance returns `FAIL` finding `verified_without_provenance`;
- candidate without provenance is allowed;
- secret-like memory content returns `FAIL` without echoing the secret.

- [ ] **Step 2: Confirm RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_memory_doctor -v
```

Expected: import failure.

- [ ] **Step 3: Implement doctor report**

```python
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
```

`memory_doctor(project_root, portfolio_root=None) -> MemoryDoctorReport` runs all checks from the spec and never modifies canonical memory.

- [ ] **Step 4: Implement `scripts/memory` transport**

Create `src/nexus_harness/memory/cli.py` with `main(argv: list[str] | None = None) -> int` using `argparse`. Create an executable `scripts/memory` following existing Harness script conventions and invoke `python3 -m nexus_harness.memory.cli "$@"` after resolving the repository's `src` path consistently with other scripts.

Supported subcommands in Plan 2.5:

```text
status
search QUERY
show MEMORY_ID
candidates
verify MEMORY_ID --commit SHA
 doctor
init-project
init-vault PATH
```

Normalize the accidental leading space in documentation: actual command is `doctor`.

No command pushes, syncs or opens a remote.

- [ ] **Step 5: Write integration proof**

Create `tests/test_memory_integration.py` implementing this exact scenario:

1. create temporary Git repo/project;
2. initialize project memory;
3. create a `CANDIDATE` invariant with approved source and related `src/auth/**`;
4. prove candidate search does not auto-return it for normal recall;
5. verify it at commit `A`;
6. search `auth session` with affected `src/auth/session.py` and prove it is top hit;
7. build a capsule and prove memory ID/provenance are present;
8. modify/commit `src/auth/session.py` as commit `B`;
9. compute freshness and prove `STALE`;
10. rebuild capsule and prove the memory leaves HOT/WARM and appears only as stale warning;
11. delete any derived SQLite index and prove search still operates through fallback;
12. pass secret-like draft and prove guard rejects it;
13. initialize no portfolio vault and prove all project behavior remains valid.

- [ ] **Step 6: Add Plan 3 API facade**

Update `src/nexus_harness/memory/__init__.py` to export these stable responsibilities:

```python
load_project_memories
write_memory
verify_memory
supersede_memory
compute_memory_freshness
search_memory
build_context_capsule
collect_memory_candidates
init_portfolio_vault
memory_doctor
```

Add a small runtime-neutral facade in `src/nexus_harness/memory/lifecycle.py` or a focused `session.py` only if needed, with exact functions Plan 3 can call:

Implement these stable functions (the implementation may live in a focused `session.py`, but they must be re-exported from `nexus_harness.memory`):

```python
def session_recall(project_root, *, project_id, query, affected_paths=(), portfolio_root=None):
    context = MemoryQueryContext(project_id=project_id, affected_paths=tuple(affected_paths))
    hits = search_memory(project_root, query, context, portfolio_root=portfolio_root)
    return build_context_capsule(project_id=project_id, diff_hash=None, hits=hits, hot_memory_ids=(), policy=load_capsule_policy())

def checkpoint_memory_candidates(path, candidates):
    payload = [item.to_json_dict() for item in candidates]
    atomic_write_json(Path(path), payload)
    return Path(path)

def restore_memory_candidates(path):
    target = Path(path)
    if not target.exists():
        return []
    return [MemoryDraft.from_json_dict(item) for item in json.loads(target.read_text(encoding="utf-8"))]

def consolidate_memory(project_root, candidates, *, current_commit, evidence_lookup=None):
    results = []
    for draft in candidates:
        record = draft.to_record()
        try:
            record = verify_record(record, current_commit=current_commit, evidence_lookup=evidence_lookup)
        except MemoryPromotionError:
            record = record  # remains CANDIDATE by policy
        results.append(write_memory(Path(project_root), record))
    return results
```

`session_recall()` returns a `ContextCapsule`; it does not modify memory. Task 6 must also implement `load_capsule_policy(path: Path | None = None) -> CapsulePolicy` by reading `core/memory/retrieval-policy.toml` with `tomllib`; the session facade uses that function.

`checkpoint_memory_candidates()` writes only structured candidate drafts to operational scratch/state, never full transcripts.

`consolidate_memory()` applies guard + promotion policy and leaves insufficiently sourced items as CANDIDATE.

- [ ] **Step 7: Validate and finalize Plan 3 integration document**

The supplied `docs/memory/PLAN-3-MEMORY-INTEGRATION.md` is the approved target contract. Compare it against the public API actually implemented in Tasks 1–8. Preserve its semantics and update exact import names only if the implementation used an equivalent public export with a recorded ruling. The final document must contain this hook contract:

```text
SessionStart
→ restore Plan 2 state when present
→ session_recall()
→ inject bounded capsule

UserPromptSubmit / new classified task
→ refresh WARM retrieval only when domain/affected paths materially change

PreCompact
→ checkpoint Plan 2 structured state
→ checkpoint_memory_candidates()

compact SessionStart
→ restore structured state
→ rebuild capsule from canonical memory

TaskCompleted after Completion Gate PASS
→ collect_memory_candidates()
→ consolidate_memory()

SessionEnd
→ flush candidate checkpoint only
```

Document failure policy:

- recall/index failure degrades to no-memory/lexical fallback and is reported;
- memory failure does not bypass or alter Completion Gate;
- no runtime may create its own canonical memory database.

- [ ] **Step 8: Update master roadmap locally**

Insert Plan 2.5 between Plan 2 and Plan 3 with dependency:

```text
Plan 2 → Plan 2.5 → Plan 3
```

Do not renumber existing Plans 3–8.

- [ ] **Step 8A: Register the approved memory amendment in the parent spec**

Append a concise section to `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md` without duplicating the full memory design:

```markdown
## 23. Approved architecture amendment — Nexus Memory

Durable engineering memory is defined by `docs/superpowers/specs/2026-08-25-nexus-harness-v4-25-memory-architecture.md`. Plan 2.5 is executed after Workflow/Graph/Quality and before Runtime Adapters/Hooks. For memory-specific architecture, provenance, retrieval, freshness and runtime integration decisions, the Plan 2.5 memory spec is the binding extension of this document.
```

If the parent spec has gained later numbered sections during Plan 2 implementation, preserve them and use the next available section number while keeping the text semantically identical.

- [ ] **Step 9: Run all memory tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_memory_models \
  tests.test_memory_store \
  tests.test_memory_guard \
  tests.test_memory_freshness \
  tests.test_memory_retrieval \
  tests.test_memory_capsule \
  tests.test_memory_lifecycle \
  tests.test_memory_portfolio \
  tests.test_memory_doctor \
  tests.test_memory_integration -v
```

Expected: PASS.

- [ ] **Step 10: Run complete Harness verification**

Run fresh:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v
scripts/validate
```

Expected: all tests PASS and validator exit 0.

- [ ] **Step 11: Run a fresh whole-branch review**

Reviewer must specifically test/inspect:

- memory overriding stronger repo/spec truth;
- candidate/stale leakage into capsules;
- secrets in Markdown/JSON/log messages;
- orphan/partial atomic pair handling;
- duplicate IDs;
- FTS dependency becoming mandatory accidentally;
- committed absolute portfolio path;
- accidental full transcript persistence;
- raw TaskState/evidence dumps copied into memory;
- lack of provenance on VERIFIED memory;
- Plan 2 Completion Gate semantics changed by memory;
- runtime-specific Claude/Cursor/Codex logic leaking into Plan 2.5;
- portfolio bridge overwriting user notes;
- non-deterministic retrieval order;
- unbounded capsule growth;
- shell injection in Git/search helpers.

Correct all BLOCKER/HIGH findings, re-review, and structurally record deferred MEDIUM/LOW debt.

- [ ] **Step 12: Commit Task 8**

```bash
git add src/nexus_harness/memory scripts/memory tests/test_memory_doctor.py tests/test_memory_integration.py docs/memory docs/superpowers/plans/nexus-harness-v4-master-roadmap.md docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md
git commit -m "feat: expose nexus memory to runtime adapters"
```

---

## Plan 2.5 Definition of Done

The Plan is not `PASS` unless fresh evidence demonstrates all of these:

1. Plan 2 was integrated locally without remote side effects.
2. Memory models/schema/policies are deterministic and validated.
3. Project memory writes Markdown+JSON atomically.
4. Secret-like content is rejected before persistence.
5. VERIFIED memory requires type-appropriate provenance.
6. Candidate memory is not normally recalled.
7. Stale memory is excluded from HOT/WARM.
8. Current repo truth has higher contradiction strength than memory.
9. Local search works without embeddings.
10. Local search works without FTS5/derived index.
11. Index deletion is recoverable.
12. Capsules remain inside configured character/item budgets.
13. Project memory works with `portfolio_root=None`.
14. Portfolio vault is plain files and requires no Obsidian plugin.
15. Bridge updates preserve manual notes.
16. Raw transcript/tool history is not auto-saved as durable memory.
17. Operational Plan 2 state is not duplicated wholesale.
18. Plan 3 stable memory API facade exists.
19. Plan 3 hook integration contract is documented.
20. Master roadmap shows Plan 2 → 2.5 → 3.
21. Full Harness test suite passes freshly.
22. `scripts/validate` exits 0 freshly.
23. Final fresh reviewer has no open BLOCKER/HIGH.
24. No push/PR/VPS/PostHog/deploy side effects occurred.

## Required final report

Return exactly:

```text
# NEXUS HARNESS V4 — PLAN 2.5 MEMORY REPORT

Status: PASS | FAIL | BLOCKED

Plan 2 integration:
- Plan 2 branch:
- Plan 2 HEAD before integration:
- main before:
- main after:
- integration method:
- fresh validation before/after:

Plan 2.5:
- branch:
- worktree:
- baseline:
- HEAD:

Tasks:
- Task 1 — Models/schema/policy
- Task 2 — Store/guard
- Task 3 — Freshness/contradiction
- Task 4 — Retrieval/index/fallback
- Task 5 — Lifecycle/promotion
- Task 6 — Context capsule
- Task 7 — Portfolio/Obsidian bridge
- Task 8 — Doctor/CLI/Plan3 contract

Commits:
- SHA message

Storage:
- project layout:
- atomic pair behavior:
- canonical vs derived files:

Lifecycle:
- statuses:
- promotion rules:
- provenance enforcement:
- supersession:

Freshness:
- related-path behavior:
- repo truth precedence:
- stale behavior:

Retrieval:
- FTS5 available in test environment:
- fallback result:
- deterministic scoring:
- index deletion recovery:

Capsule:
- HOT budget:
- WARM budget:
- candidate exclusion:
- stale exclusion/warnings:

Security/privacy:
- secret guard tests:
- sensitive memory behavior:
- absolute path scan:

Portfolio:
- vault template:
- Obsidian dependency:
- project bridge preservation:

Plan 2 integration safety:
- Completion Gate semantics changed? YES/NO
- Evidence semantics changed? YES/NO
- Quality/Security bypass introduced? YES/NO

Plan 3 contract:
- session_recall:
- checkpoint_memory_candidates:
- restore_memory_candidates:
- consolidate_memory:
- integration doc:

Tests:
- memory-specific command/result:
- complete suite command/result/count:
- scripts/validate:

Review:
- blocker:
- high:
- medium:
- low:
- fix rounds:

Inherited debt:
- Plan 1 debt current status
- Plan 2 debt current status

New technical debt:
- write `none` when empty; otherwise list each debt ID, severity, owner/target plan and reason

Rulings:
- write `none` when empty; otherwise list each ruling with decision, reason and cost if wrong

Artifacts:
- list every generated report/schema/template/integration document by repo-relative path

Remote side effects:
NONE

Next:
PLAN 3 — Runtime Adapters & Hooks
NOT STARTED
```

## Stop condition

After the report, stop. Do not merge Plan 2.5 into main, push, open a PR, start Plan 3, create the user's real Obsidian vault, access the VPS or configure any runtime globally. The user will review Plan 2 + Plan 2.5 before authorizing Plan 3.
