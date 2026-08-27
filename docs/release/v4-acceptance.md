# Nexus Harness v4 — Local acceptance

Recorded from command output and hashes on 2026-08-27. Criteria are spec §22 of `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`. Status is never PASS from narrative alone.

Worktree: `feat/v4-release-evals-doctor`
Python: 3.14.2
Git HEAD at verification: `d8fd36091792a585d741eddb264ca4d61382c94c`
Lock identity (SHA-256 of `harness.lock`): `08d8ff2bee0902a00cb8620abf588d866cf199cfb7ce70c9389d78df23b68112`
Generated hashes: 47 · engine hashes: 71 · adapter versions: claude=1, cursor=1, codex=1

No SSH. No live GitHub Project / PostHog / VPS activation. Real `~/.claude`, `~/.cursor`, and `~/.codex` were not used as install targets.

Local release gate: **PASS** (17 PASS, 0 FAIL, 3 ACTIVATION_REQUIRED of 20 criteria).

## Commands

### Full unit suite

```text
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
Ran 874 tests in 4.074s
OK
```

(`python3 -m unittest` still prints an unrelated `--dry-run` usage line during discover; suite still OK.)

### Canonical validator

```text
scripts/validate
exit 0
```

### Deterministic evals

```text
scripts/nexus evals run
nexus evals  gate=PASS
PASS     ambiguous-task
PASS     auth-security
PASS     backend-bug
PASS     database-migration
PASS     frontend-feature
PASS     github-bounded-bug-governance
PASS     long-horizon
PASS     memory-recall-freshness
PASS     multi-file-refactor
PASS     production-deploy-dry-run
PASS     runtime-incident-dedup
PASS     visual-stale-evidence
SKIP     model-quality
         model-quality evals SKIP: release PASS must not depend on Claude/Codex/Cursor/Kimi/Grok/paid inference
exit 0
```

### Compile adapters and lock diff

`dist/` in this checkout was `.gitkeep` only. Compiled first:

```text
scripts/nexus build adapters
compiled 47 generated files, 71 engine files
exit 0
```

`adapters` is a compile target alias for the project root (not `adapters/` as a render root).

```text
scripts/diff
{"extra": [], "missing": [], "modified": []}
exit 0
```

`scripts/diff` with no arguments diffs `dist/` against `harness.lock`. No unexplained generated drift.

### Doctor

After compile and `scripts/build` (release artifacts present locally, not committed):

```text
scripts/nexus --json doctor --profile local
gate=PASS
ACTIVATION_REQUIRED github
exit 0
```

```text
scripts/nexus --json doctor --profile release
gate=PASS
ACTIVATION_REQUIRED github posthog
exit 0
```

```text
scripts/nexus --json doctor --profile ci-host
gate=PASS
ACTIVATION_REQUIRED ci-profile github
exit 0
```

`--json` is a global CLI flag (`scripts/nexus --json doctor --profile local`). `ci-profile` on ci-host is ACTIVATION_REQUIRED because facts were not supplied and doctor refuses to SSH. Missing runner token is activation, not FAIL. Before `scripts/build`, `release` is also ACTIVATION_REQUIRED; that is not a local-release FAIL.

### Disposable install / rollback smoke

Tempfile home only. Real `~/.claude` / `~/.cursor` / `~/.codex` were not install targets.

Observed:

- Claude `settings.json` parsed; hooks include SessionStart, UserPromptSubmit, PreToolUse, TaskCompleted, PreCompact, PostCompact.
- Cursor `sandbox.json` parsed; `type=workspace_readwrite`; key `disabled` absent.
- Codex `config.toml` parsed; `sandbox_mode=workspace-write`.
- `AGENTS.md` contains `NEXUS WORKFLOW IS MANDATORY`.
- `detect_drift` after install: `missing=() modified=() extra=()`.
- Rollback restored the previous tree byte-for-byte (`tree_digests` equal).

## Generated file hashes (post-compile)

| Path                        | SHA-256                                                            | bytes |
| --------------------------- | ------------------------------------------------------------------ | ----: |
| `dist/claude/CLAUDE.md`     | `1622b2c64f8925bb5c9000472d187f92c7be1fb280a588e4f1dd0921b67eac61` |  1391 |
| `dist/claude/settings.json` | `8a7e690d0e0d099a189a1f0f09d5801b93f8ee258176396fc1b98a3fd0f8fc73` |  2352 |
| `dist/cursor/sandbox.json`  | `cf8c11cbaea08060f087de8f7a15627c31b2b13ef5357de6fc5279a8eeb44bf9` |   311 |
| `dist/codex/config.toml`    | `b162b288d654a2a2bb5974b32c0166d534babdbf12f8c5caecb99cddad5190ba` |   199 |
| `dist/AGENTS.md`            | `94825ed42ff3f3eee7ce3ebd6911fa97559675d101f1aa87a3904a26ce5f023f` |   963 |
| `dist/USER_RULES.md`        | `7d14af02f0c0bbf3511055825cb5ae8fe3f6863379df1367ac552a32747014a8` |   926 |
| `harness.lock`              | `08d8ff2bee0902a00cb8620abf588d866cf199cfb7ce70c9389d78df23b68112` | 19261 |

`dist/` remains gitignored except `.gitkeep`. Hashes above are of the compiled tree used for doctor/diff/smoke.

## §22 matrix

Evaluated by `nexus_harness.acceptance.evaluate_matrix`. Matrix test fails if any criterion lacks evidence, if a live row is marked PASS, or if FAIL count is not 0.

| #   | Criterion                                                                             | Status              | Evidence                                                                                                                                                                                                                                                                                                                                                                             |
| --- | ------------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | one canonical source exists per skill                                                 | PASS                | unit_test:tests/test_skill_contracts.py#test_canonical_skills_exist_once; migration_report_field:docs/migration/final-report.md#canonical skill count: 7                                                                                                                                                                                                                             |
| 2   | no byte-identical runtime skill copies are manually maintained                        | PASS                | unit_test:tests/test_migration_report.py#test_repo_report_matches_frozen_baseline_and_zero_unresolved; migration_report_field:docs/migration/final-report.md#maintained duplicate count/bytes: 0 / 0                                                                                                                                                                                 |
| 3   | system prompts trigger Nexus Workflow                                                 | PASS                | unit_test:tests/test_runtime_claude.py#test_constitution_is_minimal_and_points_to_canonical_memory; unit_test:tests/test_runtime_codex.py#test_codex_output_is_minimal_and_canonical; golden_test:tests/golden/claude/CLAUDE.md; golden_test:tests/golden/AGENTS.md; generated_config:tests/golden/.cursor/rules/nexus-workflow.mdc                                                  |
| 4   | mutable tasks cannot implement without tracked acceptance criteria and required Issue | PASS                | unit_test:tests/test_workflow.py#test_cannot_enter_implement_without_acceptance; unit_test:tests/test_workflow.py#test_tracking_requires_positive_issue_before_implement; eval_case:evals/cases/ambiguous-task.json#ambiguous-task                                                                                                                                                   |
| 5   | completion gate blocks false-done                                                     | PASS                | unit_test:tests/test_completion.py#test_failing_acceptance_blocks_done; unit_test:tests/test_hooks.py#test_completion_hook_blocks_failed_task                                                                                                                                                                                                                                        |
| 6   | repeated unchanged failures trigger diagnosis                                         | PASS                | unit_test:tests/test_failures.py#test_second_identical_failure_requests_diagnosis                                                                                                                                                                                                                                                                                                    |
| 7   | compaction preserves structured state                                                 | PASS                | unit_test:tests/test_hooks.py#test_precompact_checkpoints_state_and_candidates; unit_test:tests/test_runtime_claude.py#test_compaction_order_is_explicit                                                                                                                                                                                                                             |
| 8   | Cursor sandbox is enabled                                                             | PASS                | unit_test:tests/test_runtime_cursor.py#test_cursor_sandbox_is_not_disabled; generated_config:tests/golden/cursor/sandbox.json                                                                                                                                                                                                                                                        |
| 9   | no production target is global                                                        | PASS                | unit_test:tests/test_validate.py#test_ssh_and_scp_urls_in_core_fail; validator:src/nexus_harness/validate.py                                                                                                                                                                                                                                                                         |
| 10  | no model names appear in core constitution                                            | PASS                | unit_test:tests/test_validate.py#test_constitution_model_names_fail; validator:core/constitution.md                                                                                                                                                                                                                                                                                  |
| 11  | upstream revisions are locked                                                         | PASS                | unit_test:tests/test_skill_contracts.py#test_vendor_lock_parses_with_real_revisions; release_manifest:upstream/vendor-lock.json; release_manifest:harness.lock                                                                                                                                                                                                                       |
| 12  | dist is reproducible                                                                  | PASS                | unit_test:tests/test_compile.py#test_second_render_is_byte_identical; golden_test:tests/test_golden_adapters.py#test_rendered_files_match_reviewed_snapshots_byte_for_byte; unit_test:tests/test_release.py#test_release_manifest_is_reproducible                                                                                                                                    |
| 13  | quality/security reports are structured and ratcheted                                 | PASS                | unit_test:tests/test_quality.py#test_lower_is_better_ratchet_rejects_regression; unit_test:tests/test_security.py#test_report_to_dict_matches_schema_contract; security_scan:core/security/security-report.schema.json; release_manifest:core/quality/quality-report.schema.json                                                                                                     |
| 14  | frontend material changes produce browser evidence                                    | PASS                | unit_test:tests/test_visual.py#test_visual_evidence_is_stale_after_ui_diff_changes; eval_case:evals/cases/visual-stale-evidence.json#visual-stale-evidence                                                                                                                                                                                                                           |
| 15  | CI can run on the personal VPS with near-zero GitHub-hosted compute                   | ACTIVATION_REQUIRED | unit_test:tests/test_ci_vps_files.py#test_required_files_exist; doctor_check:src/nexus_harness/doctor.py#ci-profile                                                                                                                                                                                                                                                                  |
| 16  | affected builds prevent unnecessary server/web/worker rebuilds                        | PASS                | unit_test:tests/test_affected.py#test_web_change_does_not_build_server_image; unit_test:tests/test_cli.py#test_ci_affected_writes_plan_with_fake_git                                                                                                                                                                                                                                 |
| 17  | deployment uses immutable artifacts and no deploy-only PR                             | PASS                | unit_test:tests/test_deploy_contract.py#test_valid_service_and_digest_accepted; eval_case:evals/cases/production-deploy-dry-run.json#production-deploy-dry-run; unit_test:tests/test_pull_request.py#test_complete_issue_uses_closes_reference                                                                                                                                       |
| 18  | GitHub Issues/PRs/Project status remain synchronized with lifecycle                   | ACTIVATION_REQUIRED | unit_test:tests/test_governance_integration.py#test_bounded_bug_governance_flow; unit_test:tests/test_project_sync.py#test_stage_5_maps_to_in_progress; eval_case:evals/cases/github-bounded-bug-governance.json#github-bounded-bug-governance; doctor_check:src/nexus_harness/doctor.py#github                                                                                      |
| 19  | PostHog runtime problems can be triaged into deduplicated Issues                      | ACTIVATION_REQUIRED | unit_test:tests/test_incidents.py#test_same_error_location_has_stable_fingerprint; eval_case:evals/cases/runtime-incident-dedup.json#runtime-incident-dedup; doctor_check:src/nexus_harness/doctor.py#posthog                                                                                                                                                                        |
| 20  | nexus doctor and smoke/eval suites pass for Claude, Cursor and Codex                  | PASS                | unit_test:tests/test_doctor.py#test_local_fixture_covers_required_checks_without_false_fail; unit_test:tests/test_evals.py#test_deterministic_suite_passes_without_model_calls; unit_test:tests/test_install.py#test_disposable_home_install_parses_adapters_and_never_touches_real_homes; golden_test:tests/golden/claude/settings.json; golden_test:tests/golden/codex/config.toml |

Local release gate: **PASS** (17 PASS, 0 FAIL, 3 ACTIVATION_REQUIRED of 20 criteria)

## Live rows (not PASS)

- **15** — local CI-VPS files exist (`tests/test_ci_vps_files.py`). Live runner on the personal VPS was not activated. Doctor ci-host `ci-profile=ACTIVATION_REQUIRED`.
- **18** — local Issue/PR/project-field tests and `github-bounded-bug-governance` eval PASS the capability. Live GitHub Project node IDs were not set. Doctor `github=ACTIVATION_REQUIRED`.
- **19** — local incident fingerprint/dedup tests and `runtime-incident-dedup` eval PASS the capability. PostHog Cloud was not enabled. Doctor local `posthog=SKIP`; release `posthog=ACTIVATION_REQUIRED`.

## Release candidate (local, not committed)

`scripts/build` assembled `4.0.0-rc1` (`LOCAL_RELEASE_CANDIDATE`) at engineering HEAD `d8fd36091792a585d741eddb264ca4d61382c94c`.

- schema: `nexus-harness-release/v1`
- files in logical manifest: 794
- extracted content hashes: match `release/MANIFEST.json` (0 mismatches)
- archive path: `release/nexus-harness-v4.tar.gz` (gitignored)

Absence of live VPS / GitHub Project / PostHog does not refuse the builder.

## Security note

Criterion 13 is evidenced by structured Trivy normalization, ratchet tests, and committed schemas. This run did not execute live Trivy against a production image. Release secret scan remains pattern/filename based (`ghp_`, `github_pat_`, `phx_`, private keys). That is not a substitute for a host scan after VPS activation.
