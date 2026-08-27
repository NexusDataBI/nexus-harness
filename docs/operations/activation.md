# Nexus v4 activation

Consolidates deferred live steps from Plans 4, 5, and 7. This file is the operator sequence. It does **not** activate anything by itself.

Local release may be `PASS` while later live rows remain `ACTIVATION_REQUIRED` (spec §22 criteria 15 / 18 / 19 in `docs/release/v4-acceptance.md`). Secrets and IDs stay placeholders. Never commit tokens. Never embed an absolute user home.

Order (do not skip ahead):

1. Local release / cutover
2. Codex runtime smoke
3. Cursor runtime smoke
4. Claude runtime smoke
5. GitHub Governance
6. VPS CI
7. PostHog
8. One non-critical real project
9. Client production rollout

## 1. Local release / cutover

Follow [cutover.md](cutover.md). Preconditions: `scripts/validate`, unit tests, `scripts/nexus evals run`, `scripts/nexus build adapters`, `scripts/diff`, `scripts/nexus doctor --profile release`. Backup via `NEXUS_BACKUP_ROOT` before any install. Rollback: [rollback.md](rollback.md).

Do not treat missing GitHub Project IDs, PostHog, or VPS as a local-release failure.

## 2. Codex runtime smoke

Disposable `$CODEX_HOME` only (Codex first). Parse `dist/codex/config.toml` / installed `config.toml` (`sandbox_mode = "workspace-write"`). `scripts/nexus doctor --profile local`. `scripts/nexus evals run`. Confirm `dist/AGENTS.md` still contains `NEXUS WORKFLOW IS MANDATORY`. If the runtime cannot start, roll back immediately.

## 3. Cursor runtime smoke

Disposable `$CURSOR_HOME` (Cursor second). Parse `dist/cursor/sandbox.json` (`type` = `workspace_readwrite`, key `disabled` absent). Confirm `dist/USER_RULES.md` and `dist/.cursor/rules/nexus-workflow.mdc`. `scripts/nexus doctor --profile local`. `scripts/nexus evals run`.

## 4. Claude runtime smoke

Disposable `$CLAUDE_HOME` (Claude last). Parse `dist/claude/settings.json` (hooks include SessionStart, UserPromptSubmit, PreToolUse, TaskCompleted, PreCompact, PostCompact). `scripts/nexus doctor --profile local` then `--profile release`. `scripts/nexus evals run`. Completion-gate smoke must not false-pass (`evals/cases/ambiguous-task.json`, `tests/test_completion.py`).

## 5. GitHub Governance

Local capability is already proven (`evals/cases/github-bounded-bug-governance.json`, `tests/test_governance_integration.py`). Live IDs are not in git.

```bash
# User configuration only — do not commit
export NEXUS_GITHUB_PROJECT_ID="<github-project-node-id>"
export NEXUS_GITHUB_PROJECT_ITEM_ID="<github-project-item-id>"
# optional until this step: gh auth login
scripts/nexus doctor --profile release
```

Field names live in `core/project/project-fields.toml` (`id_stored_in_user_configuration = true`). `scripts/nexus incidents classify|render` stays local (`authorize_remote_mutation=false`). Do not create live Issues/PRs until this step is approved. Tokens: never `ghp_` / `github_pat_` in the tree.

## 6. VPS CI

Local files exist (`infra/ci-vps/install.sh`, `infra/ci-vps/nexus-ci.service`, `infra/ci-vps/nexus-ci-host-doctor.sh`, `infra/ci-vps/README.md`). `scripts/nexus doctor --profile ci-host` never SSH; missing runner/token is `ACTIVATION_REQUIRED`. Policy: `core/graph/scheduler.toml` (`target_github_hosted_minutes_per_normal_pr = 0`). See [ci-budget.md](ci-budget.md).

On the CI host only, after approval (placeholders — never commit):

```bash
export RUNNER_VERSION="<runner-version>"
export RUNNER_SHA256="<64-char-hex>"
export RUNNER_REPO_URL="https://github.com/<org>/<private-repo>"
export RUNNER_TOKEN="<github-actions-registration-token>"
# then: sudo -E ./install.sh   (from infra/ci-vps/)
# health: ./nexus-ci-host-doctor.sh
```

Rootless Docker is required. No standing production credentials on the host. Do not add the runner user to group `docker`.

## 7. PostHog

Local incident fingerprinting is proven (`evals/cases/runtime-incident-dedup.json`, `tests/test_incidents.py`). Cloud stays off until this step.

```bash
# core/observability/posthog.toml — enable locally, do not commit the key
# enabled = true
# project_id = "<posthog-project-id>"
# host = "https://<posthog-host>"
export POSTHOG_PERSONAL_API_KEY="<posthog-personal-api-key>"
scripts/nexus doctor --profile release --json
```

Never log or commit `POSTHOG_PERSONAL_API_KEY`. `scripts/nexus incidents classify|render` still must not mutate GitHub until governance (step 5) is live and remote mutation is explicitly authorized.

## 8. One non-critical real project

Pick a non-live id from `projects.toml` (`scripts/nexus project show --id <project-id>`). Run one real bounded task through each runtime (Codex, then Cursor, then Claude) under v4. Keep the v3 backup read-only until all three succeed. Do not use a client production target.

## 9. Client production rollout

Last. Requires explicit production approval, immutable image digest, and no deploy-only PR. Rehearse with `evals/cases/production-deploy-dry-run.json` (ship must stay not-ready without approval). Follow `core/policies/production.toml`. Do not run live deploy from this document.
