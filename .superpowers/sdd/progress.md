# Plan 8 ledger

Worktree: /Users/USER1/Projects/nexus-harness/.worktrees/feat-v4-release-evals-doctor
Branch: feat/v4-release-evals-doctor
PLAN_8_BASELINE: 0f806473ea0a250ba9463f075aac4ed869364435

## Plan 7 integration

Plan 7 repaired HEAD: 0f806473ea0a250ba9463f075aac4ed869364435
P7-D01 code: b3c42f3099de82de8d3dffd3e14d835d22b73d3a
main after FF: 0f806473ea0a250ba9463f075aac4ed869364435
fresh post-FF tests: 760/760 PASS; scripts/validate PASS

## Tasks

- Debt hardening gate: pending
- Task 1: DONE (CLI argparse surface; local commit; 799 tests OK)
- Task 2: DONE (nexus doctor; local commit; 817 tests OK)
- Task 3: DONE (deterministic evals; local commit; 827 tests OK)
- Task 4: DONE (final migration report; local commit; 835 tests OK)
- Task 5: DONE (reproducible release builder; local commit; see task-5-report.md)
- Task 6: DONE (acceptance matrix + disposable smoke; local commit; 867 tests OK)
- Task 7: DONE (cutover/activation docs; local commit; 872 tests OK)

## Constraints

No push. No merge of Plan 8 into main. No VPS/GitHub/PostHog/client activation.
No overwrite of real ~/.claude ~/.cursor ~/.codex.
LOCAL_RELEASE_READY only. External live checks are ACTIVATION_REQUIRED.
P7-D01 already resolved. Remaining Plan-8-target debt must end RESOLVED or ACCEPTED_RESIDUAL.
No deferred → plan-8 remaining after this plan.
