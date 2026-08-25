# Plan 1 — Canonical Core & Migration

Status: IN_PROGRESS
Started: 2026-08-25
Repo: /Users/USER1/Projects/nexus-harness
Branch: (pending worktree feat/v4-canonical-core)
Worktree: (pending)

## Inputs

- Archive: `inputs/nexus-harness-export-20260825-094238.tar.gz`
- SHA-256: `cfa547d0b27b149ba0350783da965a550f754d484ac39b0b5e9e7a5951b7b1a0`
- Planning bundle SHA-256: `edadf46aa79fd4ef81538a054f0e05186b4da9d9edf1d138c4b4a3f5b60f6ea5`
- Spec: `docs/superpowers/specs/nexus-harness-v4-final-design.md`
- Plan: `docs/superpowers/plans/2026-08-25-nexus-harness-v4-01-canonical-core-migration.md`

## Rulings

- R1: The Downloads file named `nexus-harness-export-20260825-094238.tar(1).gz` is the immutable v3 archive; stored as `inputs/nexus-harness-export-20260825-094238.tar.gz`. Hash matches.
- R2: Extracted v3 lives at `legacy/v3-export/` as read-only input. It is gitignored. The tar.gz is the immutable original.
- R3: Spec wins over legacy and over any plan contradiction.
- R4: No push, PR, remote GitHub mutation, VPS, deploy, or cloud side-effect in Plan 1.
- R5: Validator (Task 7) must exclude `inputs/`, `legacy/`, and `docs/_bundle/` from AppleDouble/.bak and leakage scans of frozen input. Canonical trees (`core/`, `skills/`, `profiles/`, `src/`, `tests/`, `upstream/`) remain in scope.
- R6: Plan 3 runtime adapters remain empty-tuple stubs in Plan 1 Task 5.

## Tasks

- Task 1: pending
- Task 2: pending
- Task 3: pending
- Task 4: pending
- Task 5: pending
- Task 6: pending
- Task 7: pending
