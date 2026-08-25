# Nexus Memory Contract for Plan 3 Runtime Adapters & Hooks

**Status before Plan 2.5:** approved target contract  
**Status after Plan 2.5:** implementation must validate this document against the actual public memory API before Plan 3 begins.

## Purpose

Plan 3 generates runtime-specific Claude/Cursor/Codex configuration and hooks. It must not implement or own a second memory system. All runtimes consume the same runtime-neutral Nexus Memory API produced by Plan 2.5.

## Public API

Plan 3 expects these responsibilities to be importable from `nexus_harness.memory`:

```python
session_recall
checkpoint_memory_candidates
restore_memory_candidates
consolidate_memory
collect_memory_candidates
memory_doctor
```

Storage/layout internals and SQLite tables are not runtime-adapter APIs.

## Hook lifecycle

### SessionStart

```text
restore Plan 2 structured state when present
→ resolve project/task identity
→ session_recall(project root, project id, task query/affected paths, optional portfolio path)
→ inject bounded Context Capsule if non-empty
```

Normal failures degrade safely:

- absent project memory → no-memory context;
- portfolio not configured → project-only recall;
- derived index unavailable → lexical fallback;
- invalid/stale memory → exclude item and report warning.

### UserPromptSubmit / new task classification

Do not reinject the whole vault on every prompt.

When a materially new task/domain/affected-path set is classified, the workflow may recompute WARM retrieval and return a newly bounded capsule/delta.

### PreCompact

```text
checkpoint Plan 2 structured operational state
→ checkpoint_memory_candidates(...)
```

Do not copy raw transcript history into durable Nexus Memory.

### Compact-related SessionStart

```text
restore Plan 2 state
→ restore candidate checkpoint
→ rebuild context capsule from canonical Markdown+JSON memory
```

A transcript/compaction summary is lower authority than the rebuilt canonical capsule and current repository state.

### TaskCompleted

Order is mandatory:

```text
Completion Gate
   ├ FAIL → do not consolidate durable memory
   └ PASS
       ↓
collect durable signals
       ↓
collect_memory_candidates(...)
       ↓
consolidate_memory(...)
```

Memory consolidation must not change Completion Gate semantics.

A memory-write failure after a valid task completion is a structured memory-health finding. It blocks completion only when durable memory itself is an explicit Acceptance Criterion of the current task.

### SessionEnd

Flush unresolved structured candidate checkpoint and memory-health summary only. Unsupported model summaries remain candidate/ephemeral; they are not silently promoted to VERIFIED.

## Claude Code adapter

Claude hook generation should wire the lifecycle above directly when the hook surface supports it.

Generated `CLAUDE.md`/settings may contain a compact statement of:

- memory authority order;
- recall hook pointer;
- stale/candidate rules;
- no-secret rule.

They may not contain the user's absolute portfolio-vault path or copied memory notes.

## Cursor adapter

Cursor generated rules use the same Nexus Memory contract.

No `.cursor/memory` or Cursor-only canonical DB is created.

If runtime hook support differs, the Nexus workflow/command invocation performs recall at equivalent task/session boundaries.

Memory access must not justify disabling the Cursor sandbox. External portfolio paths require narrow local configuration/capability rather than global home-directory access.

## Codex adapter

Codex generated `AGENTS.md`/configuration uses the same Nexus Memory APIs and policy.

No Claude-specific environment variable/path may leak into Codex memory behavior.

## Compaction invariant

```text
structured Plan 2 state + canonical Nexus Memory
→ reconstruct context after compaction
```

not:

```text
full transcript copy
→ pretend it is durable truth
```

## Golden tests required in Plan 3

Plan 3 golden/integration tests must prove:

1. Claude, Cursor and Codex point to Nexus Memory rather than separate stores.
2. Candidate memory is never configured for automatic injection.
3. Stale memory is never configured for normal HOT/WARM injection.
4. Portfolio absence does not break a runtime.
5. No generated runtime file includes an absolute user vault path.
6. No generated runtime installs or references Claude-Mem as required infrastructure.
7. No generated runtime embeds raw canonical memory content in static config.
8. PreCompact/restore semantics preserve Plan 2 state and rebuild memory context.
9. Completion FAIL prevents memory consolidation.
10. Completion PASS permits policy-valid memory consolidation.

## Local configuration

Machine-local portfolio configuration is resolved at runtime. Conceptual key:

```toml
[memory]
enabled = true
portfolio_enabled = true
portfolio_vault_path = "~/NexusMemory"
```

The actual user's path is not committed to canonical core/golden outputs.

## Failure policy

Memory is an augmentation layer.

```text
memory unavailable
→ report controlled limitation
→ continue using current repo/spec/operational state
```

Never fabricate remembered context when memory retrieval fails.

## Final Plan 3 invariant

> Every runtime receives the same durable engineering knowledge semantics; differences are transport/hook capabilities only.
