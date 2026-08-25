# Plan 2 — Workflow, Graph, Quality & Security

Status: IN_PROGRESS
Started: 2026-08-25
Repo: /Users/USER1/Projects/nexus-harness
Branch: feat/v4-workflow-graph-quality
Worktree: /Users/USER1/Projects/nexus-harness/.worktrees/feat-v4-workflow-graph-quality
PLAN_2_BASELINE: 2e0dcc11ce73ea782cd371dc98e7111dbcff91d7
Plan 1 HEAD: 2e0dcc11ce73ea782cd371dc98e7111dbcff91d7
Plan 1 worktree preserved: /Users/USER1/Projects/nexus-harness/.worktrees/feat-v4-canonical-core

## Integration

- Main before: 787c4ccd6965801d4612cde284a2adc1323b874b
- Main after / PLAN_2_BASELINE: 2e0dcc11ce73ea782cd371dc98e7111dbcff91d7
- Integration: fast-forward
- Fresh tests before merge (Plan 1 worktree): 29/29 OK, scripts/validate exit 0
- Fresh tests after merge (main): 29/29 OK, scripts/validate exit 0

## Rulings

- R8: Plan 2 schemas that already exist from Plan 1 (task-state, graph, quality-report, ratchet.toml, security-report) must be extended, never weakened.
- R9: Stage 8 in Task 1 may call a completion stub that Task 7 replaces; no false DONE shortcut.
- R10: Graph nodes are not GitHub Actions jobs.
- R11: No remote side effects. No Plan 3 adapters/hooks/VPS/GitHub/PostHog.
- R12: Plan 1 inherited debt lives in docs/migration/debt.json; do not silently drop items.

## Tasks

- Task 1: complete (commits c50c5fa..ab4229f, review clean). Lifecycle + persistence. Stage 8 stub rejects empty/FAIL; no injectable override.
- Task 2: complete (commit 32f6838). TaskGraph readiness/conflicts/invalidation; schema unchanged (R8).
- Task 3: pending
- Task 4: pending
- Task 5: complete (commit fd2e725). Trivy-only normalize; CRITICAL blocks; HIGH blocks only with FixedVersion/remediation.
- Task 6: complete (fingerprint + persist). FailureMemory serializes; TaskState.failures roundtrips through save/load without resetting the ceiling.
- Task 7: complete (commit 888f9ab). Completion gate + promote_acceptance; stage 8 uses evaluate_completion; no false DONE.
- Task 8: complete (commit de2e466). End-to-end integration: mutable task + Issue 123 + AC-001 FAIL → recorded evidence `abc` → promote → quality/security/review PASS → READY_TO_SHIP; diff `def` → FAIL (stale evidence). Test-only, existing APIs.

## Review-fix (after whole-branch review)

- Quality/security reports with `diff_hash` must match `current_diff_hash`; bare `"PASS"` still allowed.
- Finding `status: confirmed` blocks DONE; suspected/rejected do not; `confirmed: true` still works.
- GraphNode emits schema `dependencies`; invalidate cascades to PASS/SKIP dependents.
- `issue >= 1` only. Debt P2-D01..P2-D07 appended; P1-D01..P1-D05 kept.
