# Plan 1 — Canonical Core & Migration

Status: IN_PROGRESS
Started: 2026-08-25
Repo: /Users/USER1/Projects/nexus-harness
Branch: feat/v4-canonical-core
Worktree: /Users/USER1/Projects/nexus-harness/.worktrees/feat-v4-canonical-core
Baseline: 787c4ccd6965801d4612cde284a2adc1323b874b

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
- R7: Task 6 must never apply deletes under `inputs/` or `legacy/v3-export/`. Dry-run may scan the extract to record what _would_ be cleaned; apply only inside the v4 tree (or a tempfile copy). Cleanup report must not contain the tar.gz path or paths under core/skills/upstream/src/tests as delete targets.

## Tasks

- Task 1: complete (commits 787c4cc..caba180, review clean). Inventory: 2398 files, 1296 exact-duplicate extras, 0 AppleDouble, 38847022 bytes, 24976986 redundant. SHA verified independently.
- Task 2: complete (commits caba180..71eca5a, review clean). Canonical core + constitution + TOML/JSON policies. Schema required-fields tightened in fix commit. Minor from first review (no persistent TOML walk in test_config) recorded; dedicated schema contract tests added instead.
- Task 3: complete (commits 71eca5a..1b05d43, review clean). 183 SKILL.md, 97 ledger entries, 51 exact hash groups, 8 divergent same-name groups. Target always present (null for reference/obsolete). Export-only scan is correct.
- Task 4: complete (commit e46b2a9). Seven canonical SKILL.md, 14 upstream lock sources with real content_sha256. Superpowers **are** in vendor-lock (partial: TDD, systematic-debugging, SDD). Named-but-not-imported primitives and pending extracts recorded in `docs/migration/unique-heuristics.md` (not materialized).
- Task 5: complete (commits e46b2a9..d605b70, review clean). One-way compiler; empty runtime stubs; harness.lock with schema_version, canonical_hashes, generated_hashes, adapter_versions.
- Task 6: complete (commits d605b70..283e4e9, review clean). 81 planned deletes on extract copy; v4 apply no-op; archive+extract untouched; frozen-root guard.
- Task 7: complete (commits 283e4e9..d39c010, review clean). validate_repository + scripts/validate. Minors: SSH/model regex breadth; vendor JSON in upstream/ not fully parsed.
- Whole-branch review fix: canonical+adapter lock drift, `profiles/` in hashes, lock regen, Superpowers evidence, negative validator tests (IP, extra skill, R5 AppleDouble under `inputs/`). Pending extracts remain listed, not dumped.
