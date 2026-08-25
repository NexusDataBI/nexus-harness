---
name: nexus-handoff
description: "Serialize Nexus task continuation so a fresh agent restores structured state instead of compacting the constitution."
---

# nexus-handoff

Owns **serializing task continuation**. Does not classify (`nexus-workflow`), collect evidence (`nexus-verify`), or ship (`nexus-ship`).

Authoritative state is task state, git, issues, pull requests, and evidence — not the conversation.

## When

Use when a session must stop mid-task, compact, or hand work to another agent/runtime. Do not dump the constitution or restate the lifecycle spine.

## Write

Serialize, in order:

1. Task identity: repository, project, Issue URL, quality profile, intent/scope/risk.
2. Lifecycle pointer: current stage, stage_status map, SKIP reasons.
3. Acceptance criteria with current PASS/FAIL and evidence IDs.
4. Git: branch, worktree path, base commit, current diff hash.
5. Graph nodes in flight (ids, dependencies, blockers).
6. Approvals recorded and approvals still required.
7. Evidence ledger pointers (paths + diff hashes), including known staleness.
8. Suggested next skills — names only (`nexus-workflow`, Superpowers primitives, `nexus-frontend` mode, …).
9. Focus for the next session, if the user stated one.

Save under the workspace task-state location (not an OS temp dump as the sole copy). Reference specs, plans, ADRs, Issues, commits, and diffs **by path or URL**. Do not duplicate their content.

## Redact

Strip API keys, passwords, tokens, and unnecessary PII. Do not copy production data.

## Restore

A fresh agent reads this document, then reconstructs from git + Issue + evidence. If the recorded diff hash disagrees with `git`, treat evidence as stale and return to `nexus-verify`.

## Unique glue preserved from handoff

Suggested-skills section, argument-as-next-focus, and no duplication of already-captured artifacts.
