# Plan 8 ledger

Worktree: /Users/USER1/Projects/nexus-harness/.worktrees/feat-v4-release-evals-doctor
Branch: feat/v4-release-evals-doctor
PLAN_8_BASELINE: 0f806473ea0a250ba9463f075aac4ed869364435
ENGINEERING_HEAD: d8fd36091792a585d741eddb264ca4d61382c94c

## Plan 7 integration

Plan 7 repaired HEAD: 0f806473ea0a250ba9463f075aac4ed869364435
P7-D01 code: b3c42f3099de82de8d3dffd3e14d835d22b73d3a
main after FF: 0f806473ea0a250ba9463f075aac4ed869364435
fresh post-FF tests: 760/760 PASS; scripts/validate PASS

## Tasks

- Debt hardening gate: DONE (all Plan-8-target items resolved; 0 deferred)
- Task 1: DONE (CLI argparse surface)
- Task 2: DONE (nexus doctor)
- Task 3: DONE (deterministic evals)
- Task 4: DONE (final migration report)
- Task 5: DONE (reproducible release builder; scripts/build E2E PASS)
- Task 6: DONE (acceptance matrix + disposable smoke)
- Task 7: DONE (cutover/activation docs)
- Security residual repair: DONE (secret scan fixtures + CLI incident dedup)

## Constraints

No push. No merge of Plan 8 into main. No VPS/GitHub/PostHog/client activation.
No overwrite of real ~/.claude ~/.cursor ~/.codex.
LOCAL_RELEASE_READY only. External live checks are ACTIVATION_REQUIRED.
P7-D01 already resolved. Remaining Plan-8-target debt must end RESOLVED or ACCEPTED_RESIDUAL.
No deferred → plan-8 remaining after this plan.
