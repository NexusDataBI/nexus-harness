# Nexus Harness v4 — Plan 2.5 Memory Architecture

**Status:** Approved architecture extension for implementation between Plan 2 and Plan 3  
**Date:** 2026-08-25  
**Parent spec:** `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`  
**Next consumer:** `docs/superpowers/plans/2026-08-25-nexus-harness-v4-03-runtime-adapters-hooks.md`

## 1. Purpose

Plan 2 establishes operational memory for a task: structured task state, evidence, graph status, failure memory, quality/security reports and completion status. That is necessary but not sufficient for long-lived software work.

Plan 2.5 adds **durable engineering knowledge memory** that survives sessions, compaction, models and runtimes without becoming a second source of truth.

The system must answer questions such as:

- Why was an architectural decision made?
- What invariant must an agent preserve when touching a component?
- Have we seen a similar production incident before?
- What recurring lesson should influence a new implementation?
- What is the current project context without rereading the whole repository?
- Which remembered facts may now be stale because related code changed?
- What information should Claude, Cursor and Codex load at session start?

The memory layer is intentionally **not** a transcript archive, vector-database platform or replacement for GitHub/Git/repository truth.

## 2. Architectural decision

The baseline architecture is:

```text
                         NEXUS MEMORY
                              │
              ┌───────────────┴───────────────┐
              │                               │
      Operational Memory              Durable Knowledge
       Plan 2 / task state                    │
              │                   ┌───────────┴───────────┐
              │                   │                       │
              ▼                   ▼                       ▼
 ~/.nexus-harness/state/   Project Memory          Portfolio Memory
                          repository-scoped        cross-project vault
                               │                       │
                          Markdown + JSON          Markdown + JSON
                               │                       │
                               └───────────┬───────────┘
                                           ▼
                                   Derived Retrieval
                                   SQLite FTS5 or
                                   lexical fallback
                                           │
                                           ▼
                                    Context Capsule
                                           │
                       ┌───────────────────┼───────────────────┐
                       ▼                   ▼                   ▼
                    Claude              Cursor              Codex
                                           │
                                           ▼
                                       Obsidian
                                  optional human UI
```

### Core decision

**Markdown/JSON files are canonical memory. Git provides history. Derived indexes are disposable. Obsidian is an optional UI, not the database.**

No memory SaaS is introduced. No embedding API is required. No vector database is required. No Claude-Mem process is required.

## 3. Why not Claude-Mem as the canonical layer

Projects such as Claude-Mem demonstrate useful ideas: automatic session capture, progressive disclosure and local search. Those ideas are valid references, but the Nexus baseline must remain runtime-neutral and must distinguish observed activity from verified knowledge.

A transcript/session memory system tends to answer:

> What happened in previous sessions?

Nexus Memory must answer:

> What durable, verified information should influence the next task, and why should the agent trust it?

Claude-Mem or similar systems may be evaluated later as **read-only optional session-history sources**, but they may never become the canonical source for Nexus engineering decisions.

## 4. Why Obsidian is optional UI only

Obsidian works well with local Markdown and graph/backlink navigation. The Harness must not depend on Obsidian being installed, running or synchronized.

The same memory repository must remain usable with:

- command line tools;
- Claude Code;
- Cursor;
- Codex;
- a plain text editor;
- Git;
- Obsidian when the user wants a visual knowledge interface.

No Obsidian plugin is required by the baseline.

## 5. Memory layers

Memory is explicitly separated into four layers.

### L0 — Working memory

Volatile runtime context:

- current model context window;
- temporary agent reasoning context;
- scratch context for a subagent.

Properties:

- may disappear at any time;
- never authoritative;
- never relied on for task recovery.

### L1 — Operational memory

Implemented by Plans 1–2 and kept outside durable knowledge:

```text
~/.nexus-harness/state/<repo-id>/<task-id>/
├── state.json
├── evidence.jsonl
├── quality-report.json
├── security-report.json
├── failures.json
├── tool-summary.jsonl
└── handoff.md
```

Answers:

- what task is running;
- what stage is active;
- which graph nodes passed;
- which evidence is fresh;
- what failed;
- whether the task is READY_TO_SHIP.

Operational memory is not copied into durable project memory simply because it exists.

### L2 — Project memory

Durable, repository-scoped engineering knowledge.

Canonical location in a project that opts into Nexus Memory:

```text
.nexus/memory/
├── README.md
├── index.json
├── decisions/
├── invariants/
├── components/
├── patterns/
├── lessons/
└── incidents/
```

Each durable memory consists of:

```text
<category>/<memory-id>.md
<category>/<memory-id>.json
```

The Markdown file contains human-readable knowledge. The JSON sidecar contains machine-readable provenance and lifecycle state.

Project memory is versioned with the project when it represents durable project knowledge.

### L3 — Portfolio memory

Cross-project engineering knowledge stored outside individual repositories.

Default concept:

```text
NexusMemory/
├── HOME.md
├── VAULT_RULES.md
├── RETRIEVAL_PROTOCOL.md
├── projects/
├── domains/
├── patterns/
├── lessons/
├── decisions/
├── incidents/
└── .nexus-memory/
    ├── index.json
    └── cache/
```

This directory can be opened as an Obsidian Vault, but it is still a normal filesystem directory.

The path is **local user configuration**, not canonical core configuration. The Harness must never hardcode `/Users/<name>/...` in generated configuration.

## 6. Scope boundary

Plan 2.5 handles engineering/project memory only.

It does **not** create a personal-life memory system, CRM, company knowledge base, content calendar, study vault or private biography store.

Those could use the same primitives later, but mixing them now increases privacy risk and retrieval noise.

## 7. Source-of-truth precedence

Memory must never silently override stronger evidence.

For a running engineering task, precedence is:

```text
1. explicit current user instruction / approved current spec
2. security and hard governance policy
3. current executable repository state + fresh deterministic evidence
4. current canonical repository docs / ADRs / schemas
5. current GitHub Issue / PR / accepted work record
6. verified project memory
7. verified portfolio memory
8. candidate/stale memory when explicitly surfaced as uncertain
9. session transcript recollection / model recollection
```

If a memory conflicts with a higher source:

- higher source wins;
- contradiction is recorded;
- the memory is not silently used;
- the memory becomes `STALE` or `SUPERSEDED` when appropriate.

## 8. Canonical memory record

Each memory item has a Markdown body and JSON sidecar.

Example Markdown:

```markdown
# Production migrations must remain backward compatible

The server and workers may run different revisions during a rolling deploy.
Database migrations therefore must not remove or rename fields required by the previous production revision until the compatibility window has closed.

## Consequence

Use expand/migrate/contract rather than destructive one-step schema changes.

## Related

- `apps/server/src/db/`
- ADR-014
- Incident INC-2026-004
```

Example sidecar:

```json
{
  "schema_version": 1,
  "id": "mem-prod-migrations-backward-compatible",
  "type": "invariant",
  "scope": "project",
  "project_id": "sdr-platform",
  "title": "Production migrations must remain backward compatible",
  "status": "VERIFIED",
  "confidence": "HIGH",
  "created_at": "2026-08-25T18:00:00Z",
  "verified_at": "2026-08-25T18:00:00Z",
  "valid_at_commit": "abc123",
  "sources": [
    {"kind": "adr", "ref": "ADR-014"},
    {"kind": "incident", "ref": "INC-2026-004"}
  ],
  "evidence_ids": ["ev-db-compat-1"],
  "related_paths": ["apps/server/src/db/**"],
  "tags": ["database", "migration", "production"],
  "supersedes": [],
  "sensitivity": "INTERNAL"
}
```

## 9. Memory types

Baseline types are deliberately small.

### `decision`

A deliberate choice among alternatives.

Required source:

- approved spec;
- ADR;
- explicit user decision recorded in an Issue/PR/document.

### `invariant`

A rule that must remain true when code changes.

Required source:

- canonical architecture/policy;
- executable validation;
- explicit approved decision.

### `component`

Stable facts needed to work safely in a component.

Examples:

- responsibility;
- boundaries;
- important entrypoints;
- dependencies;
- non-obvious behavior.

### `pattern`

A reusable engineering approach.

Promotion requires either:

- explicit approved documentation; or
- evidence from at least two independent project occurrences.

### `lesson`

A durable lesson learned from confirmed work/bugs/reviews.

A lesson must link its originating evidence, Bug Card, Issue, PR or incident.

### `incident`

Durable summary of a confirmed production/runtime incident.

It does not replace the GitHub Issue or incident record. It captures only the reusable knowledge.

## 10. Memory lifecycle

Statuses:

```text
CANDIDATE
VERIFIED
STALE
SUPERSEDED
REJECTED
ARCHIVED
```

Transitions:

```text
observation
   ↓
CANDIDATE
   │
   ├── insufficient provenance ──→ REJECTED
   │
   ├── contradiction unresolved ─→ CANDIDATE
   │
   └── verification policy PASS ─→ VERIFIED
                                      │
                         related truth changes
                                      ↓
                                    STALE
                                      │
                          ┌───────────┴───────────┐
                          ▼                       ▼
                      reverify                replaced
                          │                       │
                          ▼                       ▼
                      VERIFIED               SUPERSEDED
```

Only `VERIFIED` memory is injected automatically into normal context capsules.

`STALE` memory may be surfaced only with an explicit stale warning when useful for investigation.

`CANDIDATE` memory is excluded from normal recall.

## 11. Candidate capture

The Harness must not persist every tool call or conversation sentence as durable memory.

Candidate-worthy signals include:

- explicit architecture decision;
- new invariant discovered and verified;
- confirmed bug root/escape cause with reusable consequence;
- recurring implementation pattern;
- non-obvious component behavior proven by code/tests;
- security constraint;
- deployment/operational lesson;
- important user-approved project convention.

Not candidate-worthy:

- "ran tests";
- "edited file X";
- transient task status;
- a one-off typo;
- a model's unsupported guess;
- raw chain-of-thought;
- full session transcript.

## 12. Promotion policy

Promotion is type-specific.

### Decision

`CANDIDATE → VERIFIED` requires a source with one of:

```text
approved_spec
adr
explicit_user_decision
accepted_issue_or_pr_decision
```

### Invariant

Requires canonical policy/spec or fresh deterministic evidence demonstrating the invariant.

### Component

Requires current repository paths and either:

- executable evidence; or
- canonical project documentation.

### Pattern

Requires explicit approved pattern documentation or at least two independent evidence sources.

### Lesson

Requires a confirmed Bug Card/review/incident and a concrete reusable consequence.

### Incident

Requires a confirmed incident/Issue identifier and a summary that excludes secrets/private payloads.

## 13. Provenance

Every verified memory must answer:

- Where did this come from?
- At which commit/release was it verified?
- What paths does it depend on?
- Which evidence or work record supports it?
- What supersedes it?

A memory with no provenance remains `CANDIDATE`.

## 14. Freshness and staleness

Staleness is deterministic where possible.

Each memory may declare `related_paths` and `valid_at_commit`.

The Harness computes freshness by comparing relevant paths between `valid_at_commit` and the current repository state.

Rules:

```text
no related paths + canonical source unchanged
→ freshness UNKNOWN or FRESH according to type policy

related paths unchanged since valid_at_commit
→ FRESH

related path changed
→ STALE_CANDIDATE

canonical source explicitly superseded
→ SUPERSEDED
```

A stale derived flag does not rewrite history automatically. It prevents normal recall and requests revalidation.

## 15. Contradiction handling

Contradictions are first-class objects, not silent overwrites.

Example:

```text
MEMORY:
"Authentication uses session cookies."

CURRENT REPO:
JWT bearer auth middleware is active.
```

Result:

```text
repo truth wins
memory excluded from normal capsule
contradiction recorded
memory freshness = STALE
```

If two verified memories conflict and neither has stronger provenance, both are excluded from automatic recall until adjudicated.

## 16. Retrieval model

Baseline retrieval is deterministic and local.

### Canonical store

Markdown + JSON.

### Derived search index

Python standard-library SQLite is allowed.

When SQLite supports FTS5:

```text
memory files
→ rebuildable SQLite index
→ FTS5 lexical search
```

When FTS5 is unavailable:

```text
memory files
→ deterministic lexical scan
```

The system must remain fully functional without the index.

### No embeddings in baseline

No embedding service, Chroma, Qdrant, Pinecone, pgvector or other vector database is introduced by Plan 2.5.

A later eval may justify semantic indexing only if deterministic retrieval demonstrably misses relevant memories.

## 17. Retrieval scoring

The baseline scorer is inspectable and deterministic.

Recommended weights:

```text
same project                   +20
exact related-path overlap     +16
related-path prefix overlap    +10
exact tag match                +8 each, max +24
title token match              +5 each, max +20
body token match               +2 each, max +20
memory type requested          +10
verified + fresh               +12
verified + freshness unknown   +4
stale                          -30
candidate                      excluded by default
superseded/rejected            excluded
```

Ties resolve by:

1. higher provenance strength;
2. more recent verified time;
3. stable memory ID lexical order.

## 18. Tiered retrieval

The Harness adopts progressive disclosure without copying a third-party implementation.

### HOT

Always-small project orientation:

- project identity;
- current task/Issue pointer;
- critical invariants;
- current architectural decisions relevant to active paths;
- top current gotchas.

### WARM

Retrieved when task relevance warrants it:

- component facts;
- related lessons;
- patterns;
- prior incidents;
- relevant decisions.

### COLD

Search-only:

- historical incidents;
- superseded context;
- long-form research;
- archived project material.

## 19. Context capsule

A Context Capsule is a generated, non-canonical rendering of relevant verified knowledge for a runtime.

It must include provenance pointers and freshness status.

Example:

```text
NEXUS CONTEXT CAPSULE
Project: sdr-platform
Generated for diff: abc123

HOT
- [INV] Production migrations remain backward compatible.
  source: mem-prod-migrations-backward-compatible
- [DEC] Conversation state uses Redis with DB persistence fallback.
  source: mem-conversation-state

WARM
- [LESSON] Role fixtures must mirror production grants.
  source: mem-role-fixtures-production

STALE/CONFLICT WARNINGS
- mem-auth-session-cookie was excluded because related auth paths changed.
```

Capsules are disposable. They are never edited manually.

## 20. Context budgets

The baseline must remain tokenizer-independent.

Use character/line limits rather than a model-specific tokenizer.

Default policy:

```toml
[capsule]
hot_max_chars = 6000
warm_max_chars = 10000
max_items = 16
max_item_chars = 1800
include_stale_warnings = true
```

The renderer truncates at item boundaries; it never silently cuts provenance metadata from an included item.

## 21. Project memory structure

Canonical template:

```text
.nexus/memory/
├── README.md
├── index.json
├── decisions/
├── invariants/
├── components/
├── patterns/
├── lessons/
└── incidents/
```

`index.json` is rebuildable from JSON sidecars. It is committed only if the project policy chooses a committed deterministic index. The baseline Harness treats it as generated/rebuildable.

## 22. Portfolio vault structure

Template supplied by the Harness:

```text
memory-vault-template/
├── HOME.md
├── VAULT_RULES.md
├── RETRIEVAL_PROTOCOL.md
├── projects/
├── domains/
├── patterns/
├── lessons/
├── decisions/
├── incidents/
└── .nexus-memory/
    └── README.md
```

### Project bridge cards

`projects/<project-id>.md` is a bridge, not a duplicate project wiki.

It contains:

- project identity;
- repository identifier;
- status/focus pointer when available;
- link/path to canonical project memory;
- selected cross-project memory links.

Project bridge cards must clearly mark generated/derived sections.

## 23. Portfolio promotion

Project-specific facts stay in project memory.

A project memory is promoted to portfolio memory only when it is reusable across projects.

Examples:

```text
"SDR API endpoint /foo is idempotent"
→ project only

"Webhook consumers require stable idempotency keys"
→ eligible for portfolio pattern
```

Portfolio promotion creates a new global memory with source links to contributing project memories. It does not move/delete the source memories.

## 24. Security and privacy

Memory persistence is a data-exfiltration boundary.

Memory must reject or redact:

- API keys;
- access tokens;
- passwords;
- private keys;
- cookie/session secrets;
- production credentials;
- `.env` values;
- raw customer payloads unless explicitly approved and sanitized;
- sensitive personal data unrelated to engineering need.

The baseline uses local deterministic guard patterns from the existing Harness security policy. It does not add a second security scanner.

Trivy remains the sole baseline scanner for repository/security gates. Memory guard logic is input validation, not a competing scanner product.

## 25. Sensitive memory policy

Allowed sensitivity values:

```text
PUBLIC
INTERNAL
CONFIDENTIAL
```

Baseline automatic context injection includes:

- PUBLIC;
- INTERNAL.

`CONFIDENTIAL` requires an explicit task/context permission and may not be copied into portfolio memory automatically.

Secrets are never valid memory at any sensitivity level.

## 26. Integration with Plan 2 task state

Plan 2.5 consumes, but must not weaken, Plan 2.

Interfaces:

```text
TaskState
Evidence
TaskGraph
FailureMemory
CompletionResult
```

Memory capture happens **after** the relevant fact has evidence. Memory must never be used to promote an Acceptance Criterion or bypass a current Quality/Security gate.

Operational task state remains the recovery authority for an in-progress task.

## 27. Integration with task graph invalidation

Memory may declare related paths.

When the graph sees relevant path changes, memory freshness may be recomputed.

Graph invalidation and memory staleness are separate:

```text
graph node invalidation
→ re-run required task evidence

memory staleness
→ exclude/update durable knowledge recall
```

Neither substitutes for the other.

## 28. Integration with failure memory

Plan 2 failure memory records repeated execution failures.

Only reusable findings become durable memory.

Example:

```text
FailureMemory:
"vitest failed twice because port 5432 busy"
→ operational only

Confirmed recurring root cause:
"integration tests must allocate isolated DB ports"
→ durable lesson candidate
```

## 29. Integration contract for Plan 3

Plan 3 must use Plan 2.5 APIs rather than invent runtime-specific memory.

Required runtime-neutral hook actions:

```text
session_recall
checkpoint_state
restore_state
collect_memory_candidates
consolidate_memory
memory_health
```

### SessionStart

```text
resolve repo/task identity
→ restore operational state when applicable
→ build fresh Context Capsule
→ inject bounded HOT/WARM memory
```

### UserPromptSubmit / task classification

When a new task changes domain/affected paths:

```text
recompute relevant WARM retrieval if necessary
```

It must not blindly inject the whole memory vault every prompt.

### PreCompact

```text
checkpoint operational state
→ persist unresolved memory candidates separately
```

Do not promote memories merely because compaction is about to occur.

### compact-related SessionStart

```text
restore TaskState/ledger
→ rebuild capsule from canonical memory
```

Do not rely on a copied transcript summary as the source of truth.

### TaskCompleted

After completion gate passes:

```text
collect durable-memory candidates
→ verify provenance/policy
→ write verified memory or leave candidate
```

Memory write failure must not retroactively falsify task completion, but it must be reported as a non-blocking memory-health finding unless the task explicitly required memory output.

### SessionEnd

```text
flush safe candidate metadata
→ never write unsupported guesses as VERIFIED
```

## 30. Runtime-neutral API contract

Plan 2.5 must expose functions with these stable responsibilities:

```python
load_project_memories(project_root) -> list[MemoryRecord]
write_memory(project_root, draft, policy) -> MemoryRecord
verify_memory(project_root, memory_id, verification) -> MemoryRecord
compute_memory_freshness(record, repo_state) -> FreshnessResult
search_memory(query, context, policy) -> list[MemoryHit]
build_context_capsule(context, hits, policy) -> ContextCapsule
collect_memory_candidates(task_state, evidence, findings) -> list[MemoryDraft]
init_portfolio_vault(target_dir) -> Path
memory_doctor(project_root, portfolio_root=None) -> MemoryDoctorReport
```

Names may be packaged in focused modules, but Plan 3 must not require runtime-specific storage semantics.

## 31. Local configuration

Canonical core defines policy; machine-specific paths live in local user configuration.

Concept:

```toml
[memory]
enabled = true
portfolio_enabled = true
portfolio_vault_path = "~/NexusMemory"
```

The committed core may define the setting key and defaults, but must not commit a specific user's absolute home path.

If no portfolio vault is configured:

- project memory still works;
- runtime recall still works;
- portfolio search returns a controlled `NOT_CONFIGURED` result;
- no task crashes solely because Obsidian/portfolio memory is unavailable.

## 32. Memory commands

Plan 2.5 baseline command surface:

```text
nexus memory status
nexus memory search <query>
nexus memory show <id>
nexus memory candidates
nexus memory verify <id>
nexus memory doctor
nexus memory init-project
nexus memory init-vault <path>
```

The implementation may expose these through `scripts/memory` plus Python module entrypoints until a unified `nexus` CLI exists.

No command performs remote synchronization in Plan 2.5.

## 33. Doctor checks

Memory doctor validates:

- project memory layout;
- JSON sidecar schema;
- duplicate IDs;
- orphan Markdown/JSON pairs;
- forbidden secrets/patterns;
- provenance on VERIFIED memories;
- stale/superseded state consistency;
- related path validity where possible;
- index rebuildability;
- capsule budget;
- portfolio vault layout when configured.

## 34. Git behavior

Project durable memory can be committed with code because it documents durable project knowledge.

Operational state remains outside Git.

Derived SQLite indexes/caches are gitignored.

Portfolio memory may be its own local/private Git repository, but Plan 2.5 does not create or push a remote.

## 35. Multi-runtime behavior

Claude, Cursor and Codex must see the same canonical project/portfolio memory.

No runtime owns a separate canonical `memory.md` truth.

Generated runtime files may contain only:

- memory policy summary;
- command/hook pointers;
- current generated context capsule when the runtime supports it.

Any runtime cache is disposable.

## 36. No hidden auto-write

Automatic candidate collection is allowed.

Automatic `VERIFIED` promotion is allowed only when deterministic promotion rules are satisfied.

An LLM summary by itself is not deterministic evidence.

If provenance is insufficient:

```text
write CANDIDATE
not VERIFIED
```

## 37. Durability and atomic writes

JSON and Markdown pairs are written atomically:

```text
validate draft
→ write temp Markdown
→ write temp JSON
→ fsync where practical
→ rename into canonical paths
```

A partial pair must be detected by doctor and never loaded as VERIFIED memory.

## 38. Memory IDs

IDs are stable, readable and collision-safe.

Format:

```text
mem-<type>-<slug>-<8hex>
```

Example:

```text
mem-invariant-prod-migration-4a12f0c9
```

The 8-hex suffix derives from a stable hash of project/scope/type/title at creation time.

Renaming a title does not change the existing ID.

## 39. Index and cache ownership

Derived files live outside canonical note directories:

```text
~/.nexus-harness/memory-cache/<repo-id>/memory.db
~/.nexus-harness/memory-cache/portfolio/memory.db
```

They can be deleted at any time and rebuilt from Markdown/JSON.

A corrupted index must degrade to lexical filesystem search, not block work.

## 40. Evals and golden scenarios

Required Plan 2.5 scenarios:

1. verified memory is recalled for matching project/path;
2. candidate memory is not auto-injected;
3. stale memory is excluded and warned;
4. current repo truth wins over conflicting memory;
5. secret-like content is rejected;
6. duplicate memory ID is rejected;
7. project memory works with no portfolio vault;
8. FTS index deletion is recoverable;
9. lexical fallback returns relevant memory;
10. capsule stays within configured budget;
11. cross-project promotion keeps source provenance;
12. session candidate capture does not persist raw transcript;
13. operational state is never copied wholesale to durable memory;
14. Plan 3 can call recall/checkpoint/consolidation APIs without runtime-specific code.

## 41. Files introduced by Plan 2.5

Canonical policy/schema:

```text
core/memory/
├── memory-record.schema.json
├── memory-policy.toml
└── retrieval-policy.toml
```

Runtime-neutral implementation:

```text
src/nexus_harness/memory/
├── __init__.py
├── models.py
├── store.py
├── freshness.py
├── retrieval.py
├── lifecycle.py
├── capsule.py
├── portfolio.py
├── guard.py
└── doctor.py
```

Supporting templates/commands:

```text
templates/memory/
├── project-memory/README.md
└── portfolio-vault/
    ├── HOME.md
    ├── VAULT_RULES.md
    └── RETRIEVAL_PROTOCOL.md

scripts/memory
```

Tests:

```text
tests/test_memory_models.py
tests/test_memory_store.py
tests/test_memory_freshness.py
tests/test_memory_retrieval.py
tests/test_memory_lifecycle.py
tests/test_memory_capsule.py
tests/test_memory_portfolio.py
tests/test_memory_guard.py
tests/test_memory_doctor.py
tests/test_memory_integration.py
```

## 42. Plan 3 changes required after Plan 2.5

Plan 3 remains the runtime-adapter plan, but its hook implementation must consume Nexus Memory.

Plan 3 Task 2 Claude hooks:

- `SessionStart` calls `session_recall`;
- `PreCompact` calls checkpoint, not transcript duplication;
- compact restore rebuilds memory capsule;
- `TaskCompleted` may collect/consolidate candidates after Completion Gate PASS;
- `SessionEnd` flushes candidate metadata safely.

Plan 3 Task 3 Cursor:

- generated rules reference Nexus Memory recall command/API;
- no separate Cursor memory database is created.

Plan 3 Task 4 Codex:

- generated AGENTS/config references the same Nexus Memory contract;
- no Claude-specific memory path leaks into Codex.

Plan 3 Task 5 hooks:

- runtime-neutral hook handlers are wired to Plan 2.5 APIs;
- memory failures are structured and degrade safely.

Golden adapter snapshots must prove that all runtimes point to the same canonical memory contract.

## 43. Plan 5 integration later

Plan 5 introduces formal GitHub Project Governance and project registry.

Plan 2.5 must not wait for Plan 5.

For now APIs accept `project_id`/`repo_id` as input. Plan 5 later becomes the preferred source for project identity and portfolio bridge metadata.

## 44. Cost policy

Baseline recurring cost:

```text
Memory store       R$ 0
SQLite             R$ 0
Git                R$ 0
Obsidian desktop   R$ 0 baseline use
Embedding API      not used
Vector DB          not used
Memory SaaS        not used
```

Obsidian Sync is not a baseline requirement.

## 45. External references used as design inspiration

The architecture borrows principles, not dependencies, from:

- `mithunyc/obsidian-agent-memory`: context capsules, tiered retrieval and repo-truth-over-memory contradiction handling.
- Claude-Mem ecosystem: progressive disclosure and cross-session recall.
- local FTS-based agent memory systems: canonical local files plus derived full-text indexes.

These repositories are references/upstream research only unless explicitly added to `upstream/vendor-lock.json` as documentation references. Their runtime is not installed by Plan 2.5.

## 46. Success criteria

Plan 2.5 is complete when all of the following are evidenced:

1. Project durable memory has a canonical Markdown+JSON schema.
2. Verified memory requires provenance.
3. Candidate memory is excluded from automatic recall.
4. Stale memory is excluded from normal recall.
5. Contradictions prefer stronger current truth and are surfaced.
6. No secrets can be persisted as memory by baseline APIs.
7. Retrieval works without embeddings.
8. Retrieval works when FTS5/index is unavailable.
9. Derived indexes can be deleted and rebuilt.
10. Context capsules have deterministic size limits.
11. Operational task state is not duplicated wholesale into durable memory.
12. Project memory works without an Obsidian vault.
13. Portfolio memory works as ordinary Markdown/JSON and can be opened by Obsidian.
14. Portfolio promotion preserves source provenance.
15. No absolute user path is committed to canonical core.
16. Plan 2 state/evidence APIs remain authoritative and unchanged in semantics.
17. Plan 3 receives stable recall/checkpoint/consolidation APIs.
18. Claude/Cursor/Codex can share one memory source after Plan 3.
19. Full unittest suite remains green.
20. `scripts/validate` remains green.

## 47. Explicit non-goals

Not part of Plan 2.5:

- semantic vector embeddings;
- cloud memory synchronization;
- Obsidian Sync configuration;
- custom Obsidian plugin;
- browser UI for memory;
- personal-life memory;
- customer CRM knowledge;
- storing full chat transcripts;
- automatically saving chain-of-thought;
- replacing GitHub Issues;
- replacing ADR/spec documentation;
- replacing Plan 2 evidence/state;
- configuring Claude/Cursor/Codex adapters themselves — that is Plan 3.

## 48. Final invariant

The governing rule is:

> **Memory helps the agent find context; memory never grants permission, proves correctness or overrides current truth.**

