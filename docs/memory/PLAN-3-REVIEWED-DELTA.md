# Nexus Harness v4 — Plan 3 Reviewed Execution Delta

This amendment is binding for execution of:

`docs/superpowers/plans/2026-08-25-nexus-harness-v4-03-runtime-adapters-hooks.md`

It reflects the actual Plan 2 + Plan 2.5 implementation reviewed on 2026-08-25.

## Authority

Read in this order:

1. explicit user instructions;
2. security/hard policy;
3. `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`;
4. `docs/superpowers/specs/2026-08-25-nexus-harness-v4-25-memory-architecture.md`;
5. `docs/memory/PLAN-3-MEMORY-INTEGRATION.md`;
6. this reviewed delta;
7. original Plan 3 implementation plan;
8. runtime legacy behavior.

## Phase A — finish Plan 2.5 before integration

On `feat/v4-memory`:

1. fix `git diff --check` findings;
2. close P25-D01;
3. close P25-D03;
4. close P25-D04;
5. run memory-focused tests;
6. run full tests;
7. run `scripts/validate`;
8. run `git diff --check main..HEAD` and require zero findings;
9. fresh review;
10. commit fixes locally.

Only after this gate may Plan 2.5 fast-forward into `main`.

## Phase B — Plan 3 Runtime Hardening Gate

Create a fresh Plan 3 worktree. Before or alongside the earliest tasks, close:

- P1-D01;
- P1-D03;
- P2-D01;
- P2-D02;
- P2-D05;
- P2-D06;
- P2-D07.

Each debt must get a regression test and update `docs/migration/debt.json` to `resolved` with resolution commit/evidence where the existing schema permits it.

### P2-D06 boundary

Do not create remote GitHub Issues in Plan 3. Implement only deterministic local enforcement:

```text
tracking_required + implementation-bearing intent + Stage 5
→ valid positive issue id required
→ otherwise BLOCKED / cannot advance
```

Actual GitHub Issue creation/synchronization remains Plan 5.

## Runtime-neutral memory integration

Adapters and hooks consume only public `nexus_harness.memory` exports. Do not access memory storage internals or SQLite schema directly.

Required public responsibilities already available:

- `session_recall`
- `checkpoint_memory_candidates`
- `restore_memory_candidates`
- `collect_memory_candidates`
- `consolidate_memory`
- `memory_doctor`

### SessionStart

```text
restore persistent Plan 2 TaskState
→ restore memory candidate checkpoint when compact/resume
→ resolve project/task context
→ session_recall(...)
→ inject bounded capsule only
```

Failure is fail-soft for memory and fail-closed for governance:

- no memory/portfolio → continue without fabricated context;
- corrupt memory → structured warning, affected item excluded;
- Completion/approval/security state missing or invalid → do not infer PASS.

### UserPromptSubmit

Do not re-inject the entire vault. Refresh WARM retrieval only when task classification, query domain, or affected paths materially change.

### PreCompact

Persist both:

1. full structured Plan 2 operational state required for deterministic resume;
2. unresolved `MemoryDraft` candidates via `checkpoint_memory_candidates`.

Never persist raw transcript as canonical Nexus Memory.

### Compact SessionStart

Restore operational state first, then candidates, then rebuild a new capsule from canonical current memory.

### TaskCompleted

Order is mandatory:

```text
Completion Gate
  FAIL → block; no durable memory consolidation
  READY_TO_SHIP / valid completion state
     → collect durable signals
     → collect_memory_candidates(...)
     → consolidate_memory(...)
```

A memory write failure must never turn a failed Completion Gate into success. If durable memory itself is not an AC, report memory health separately.

### SessionEnd

Flush unresolved candidate checkpoint and memory health summary only.

## Runtime adapters

### Claude

Use rich native hooks where supported. Generated files may reference Nexus Memory policy/APIs, but never include:

- raw memory notes;
- absolute portfolio path;
- Claude-Mem requirement;
- client-specific paths/secrets;
- hardcoded model names.

### Cursor

Use the same memory semantics. If hook surfaces differ, expose a generated runtime-neutral command/rule path that invokes the common hook engine. Do not create `.cursor/memory` and do not disable sandbox for memory access.

### Codex

Use the same memory semantics via AGENTS/config and the common hook/command engine. No Claude env/path leakage.

## Required additional golden/integration tests

In addition to original Plan 3 tests, prove:

1. all three runtimes point to Nexus Memory, not runtime-owned memory;
2. no generated runtime contains an absolute vault path;
3. no generated runtime contains canonical memory bodies;
4. candidate/stale/confidential memory is not configured for automatic injection;
5. SessionStart survives absent portfolio;
6. SessionStart survives schema-invalid memory with a structured warning;
7. explicit CURRENT_REPO contradiction excludes the contradicted memory from normal capsule;
8. PreCompact → restart restores TaskState completion fields and memory candidates;
9. Completion FAIL cannot consolidate memory;
10. valid completion may consolidate policy-valid candidates;
11. installed/generated drift remains deterministic;
12. generated output contains no project IP/SSH/client/model leakage.

## Final gate

Plan 3 cannot report PASS until all are green:

- targeted debt tests;
- adapter tests;
- hook tests;
- install/rollback tests;
- golden tests;
- memory integration tests;
- full unittest discovery;
- `scripts/validate`;
- `git diff --check <plan3-base>..HEAD`.
