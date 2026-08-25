# Plan 3 Memory Integration Delta

**Purpose:** This document is a binding amendment to `docs/superpowers/plans/2026-08-25-nexus-harness-v4-03-runtime-adapters-hooks.md` after Plan 2.5 is integrated locally.

Plan 3 remains responsible for Claude, Cursor, Codex, runtime hooks, generated outputs, install/rollback and golden adapter compilation. Plan 3 must **consume** Nexus Memory rather than create a separate memory implementation.

## 1. Specs Plan 3 must read

Before Plan 3 Task 1:

1. `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`
2. `docs/superpowers/specs/2026-08-25-nexus-harness-v4-25-memory-architecture.md`
3. `docs/memory/PLAN-3-MEMORY-INTEGRATION.md` produced by Plan 2.5 implementation
4. the original Plan 3 implementation plan

For memory-related conflicts, the Plan 2.5 memory spec is the authoritative extension of the v4 design.

## 2. Stable runtime-neutral APIs expected from Plan 2.5

Plan 3 may import only the public memory API. It must not depend on project-memory directory internals or SQLite tables.

Required responsibilities:

```python
from nexus_harness.memory import (
    session_recall,
    checkpoint_memory_candidates,
    restore_memory_candidates,
    consolidate_memory,
    collect_memory_candidates,
    memory_doctor,
)
```

If Plan 2.5 packages one of these in a submodule but exports it through `nexus_harness.memory`, Plan 3 must use the public export.

## 3. Plan 3 Task 1 delta — runtime adapter contract

`runtime_common.py` gains a runtime-neutral memory capability declaration, not storage logic.

Generated runtime docs may say:

```text
Nexus Memory is the canonical cross-session engineering memory layer.
Use runtime hooks/commands to recall bounded context. Never create a second canonical runtime memory database.
```

Generated files must not contain:

- the user's absolute vault path;
- copied project memories;
- a full memory database;
- model-specific memory policy differences.

Machine-local paths are resolved at runtime from local config.

## 4. Plan 3 Task 2 delta — Claude

Claude is the richest hook surface.

Required behavior:

### `SessionStart`

Order:

```text
load/restore Plan 2 structured task state
→ resolve project/task context
→ call session_recall(...)
→ inject bounded Context Capsule when non-empty
→ continue normal session-init result
```

Failure behavior:

- FTS/index failure: retrieval module falls back;
- project memory unavailable: continue with structured warning;
- portfolio not configured: no error;
- corrupt canonical memory causing doctor-level failure: do not inject affected memory; report warning.

### `UserPromptSubmit`

Do not inject the full capsule every prompt.

Prompt routing may refresh WARM recall only when classification/affected paths materially change. The hook result must be size-bounded.

### `PreCompact`

Order:

```text
checkpoint Plan 2 structured state
→ checkpoint_memory_candidates(...)
```

Do not serialize the whole transcript into Nexus Memory.

### compact-related `SessionStart`

```text
restore Plan 2 task state
→ restore candidate checkpoint
→ rebuild Context Capsule from canonical memory
```

The restored transcript summary is not memory authority.

### `TaskCompleted`

Only after deterministic Completion Gate PASS:

```text
signals = durable signals from task/bug/review artifacts
candidates = collect_memory_candidates(...)
consolidate_memory(...)
```

If memory consolidation fails, report `memory_health=FAIL` or warning according to the error. It must not turn an already valid Completion Gate into PASS if it was FAIL, nor bypass the gate. Memory output is blocking only if the current task's Acceptance Criteria explicitly require memory documentation.

### `SessionEnd`

Flush unresolved structured candidates/checkpoint only. Never promote unsupported LLM summaries to VERIFIED.

## 5. Plan 3 Task 3 delta — Cursor

Cursor generated rules must state the same source-of-truth and memory rules.

Cursor must not get a separate `.cursor/memory` canonical store.

When a hook-equivalent capability is unavailable, generated instructions invoke the same local `scripts/memory`/public API through the Harness workflow at session/task boundaries.

Sandbox policy must allow reading configured local Nexus state/memory only according to existing filesystem policy. Do not globally grant arbitrary home-directory access merely to reach a portfolio vault. If explicit local configuration points outside allowed roots, the runtime must request/declare the narrow path capability rather than disabling the sandbox.

## 6. Plan 3 Task 4 delta — Codex

Codex `AGENTS.md`/config references Nexus Memory behavior, not Claude-Mem or Claude-specific paths.

Codex must:

- use the same project memory;
- use the same portfolio configuration;
- use the same capsule policy;
- respect the same stale/candidate exclusions.

No `CLAUDE_CODE_*` memory variable may leak into Codex output.

## 7. Plan 3 Task 5 delta — hook engine

`src/nexus_harness/hooks.py` remains the runtime-neutral lifecycle hook transport.

Add focused handlers or helper calls for:

```text
session_recall
checkpoint_memory
restore_memory
consolidate_memory
memory_health
```

Do not duplicate memory lifecycle logic inside `hooks.py`; delegate to `nexus_harness.memory`.

Required hook tests:

1. SessionStart with verified memory includes bounded capsule.
2. SessionStart with candidate-only memory injects nothing.
3. SessionStart with stale memory excludes it and may warn.
4. PreCompact checkpoints candidate metadata but not raw transcript.
5. TaskCompleted does not consolidate memory when Completion Gate fails.
6. TaskCompleted after Completion PASS may consolidate a provenance-valid candidate.
7. Portfolio not configured does not block SessionStart.
8. Memory retrieval error degrades safely and does not fabricate context.

## 8. Plan 3 Task 6 delta — install/drift

Atomic install includes any generated memory hook pointers/config keys, but **does not install the user's real portfolio vault automatically**.

`nexus memory init-vault <path>` remains an explicit user action.

Installed generated files are drift-detected as before. Canonical project memories are user/project content and are not generated adapter artifacts.

## 9. Plan 3 Task 7 delta — golden adapters

Golden output must assert:

- Claude/Cursor/Codex all reference the same Nexus Memory contract.
- no runtime output hardcodes `/Users/.../NexusMemory`.
- no runtime output installs Claude-Mem.
- no runtime output embeds raw memory notes.
- no runtime output disables sandbox for memory access.
- generated memory instructions are bounded pointers, not large copied context.

## 10. Plan 3 completion additions

Plan 3 cannot PASS until fresh tests prove:

```text
same canonical memory
→ Claude recall PASS
→ Cursor contract PASS
→ Codex contract PASS
```

and:

```text
candidate memory
→ no automatic injection

stale memory
→ no automatic injection

portfolio absent
→ runtime still works

compact/restart
→ operational state restored + canonical capsule rebuilt
```

