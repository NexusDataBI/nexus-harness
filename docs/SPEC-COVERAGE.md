# Spec Coverage Matrix

This matrix is the self-review for the implementation plans. Every final design success criterion has an implementation owner and release evidence.

| # | Success criterion | Plan owner | Evidence |
|---:|---|---|---|
| 1 | One canonical source per skill | P1 | `test_skill_contracts.py`, migration ledger |
| 2 | No manually maintained byte-identical runtime copies | P1/P3 | inventory + compiler/golden tests |
| 3 | System prompts trigger Nexus Workflow | P3 | runtime golden tests |
| 4 | Mutable tasks require Issue + acceptance before implementation | P2/P5 | workflow + tracking integration tests |
| 5 | Completion gate blocks false done | P2 | `test_completion.py` |
| 6 | Repeated unchanged failures trigger diagnosis | P2 | `test_failures.py` |
| 7 | Compaction preserves structured task state | P3 | Claude hook tests |
| 8 | Cursor sandbox enabled | P3 | `test_runtime_cursor.py` |
| 9 | No production target is global | P1/P3 | validator + adapter leakage tests |
| 10 | No model names in core constitution | P1/P3 | validator + adapter tests |
| 11 | Upstream revisions locked | P1/P8 | `vendor-lock.json` validation |
| 12 | `dist` reproducible | P1/P3/P8 | compile/golden/release tests |
| 13 | Structured ratcheted quality/security reports | P2 | quality/security tests |
| 14 | Material frontend changes produce browser evidence | P6 | frontend integration test |
| 15 | CI can run on personal VPS with near-zero GitHub-hosted compute | P4 | workflow render + CI budget report + CI-host doctor |
| 16 | Affected builds prevent unnecessary image builds | P4 | affected-component tests |
| 17 | Immutable deployment and no deploy-only PR | P4/P5 | deploy-manifest + PR governance tests |
| 18 | GitHub Issue/PR/Project synchronized with lifecycle | P5 | governance integration test |
| 19 | PostHog runtime problems triage into deduplicated Issues | P7 | incident integration test |
| 20 | Doctor/smoke/evals pass for all runtimes | P8 | acceptance matrix + golden/eval/doctor tests |

## Scope review

The final architecture was decomposed into eight plans because it contains independent subsystems. Plan 1 establishes the shared canonical contract. Plans 2 and 3 can proceed independently after Plan 1. Plan 4 consumes both. Plans 5–7 consume stable shared contracts and can proceed in parallel after their dependencies. Plan 8 is the integration/release gate.

## Placeholder review

The planning bundle contains no `TBD`, `TODO`, `implement later`, unresolved fake revision, or generic “similar to another task” instruction. Runtime values that are necessarily environment-specific are represented as configuration inputs and are listed in `USER-ACTIONS.md`, not invented in source.

## Type/interface review

Cross-plan interfaces intentionally stabilize around:
- `TaskState`
- `TaskGraph` / `GraphNode`
- `Evidence`
- `QualityReport`
- `SecurityReport`
- `CompletionResult`
- `ProjectRegistry`
- `GitHub`
- `DeployManifest`
- `VisualEvidence`
- `IncidentCandidate`

Later plans consume these names rather than redefining parallel versions.
