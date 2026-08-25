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

- Task 1: pending
- Task 2: pending
- Task 3: pending
- Task 4: pending
- Task 5: pending
- Task 6: pending
- Task 7: pending
- Task 8: pending
