# Nexus doctor

`scripts/nexus doctor` reports whether the harness is ready, degraded, or blocked. It is local and hermetic: no SSH, no live GitHub API, no PostHog HTTP, no VPS login.

## Command

```bash
scripts/nexus doctor --profile local
scripts/nexus doctor --profile release
scripts/nexus doctor --profile ci-host
scripts/nexus doctor --json --profile local
scripts/nexus doctor --profile release --project web
```

`--json` prints `dumps_report` JSON on stdout only. Secrets are never included.

Statuses: `PASS` | `FAIL` | `WARN` | `SKIP` | `ACTIVATION_REQUIRED`.

Exit `1` only when the gate is `FAIL`. `ACTIVATION_REQUIRED` does not fail local or release doctor.

## Profiles

| Profile   | Meaning                                                                                                                                          |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `local`   | Local harness usability (Python, Git, canonical tree, generated dist, registry, task-state, memory policy). Optional SaaS is `SKIP`.             |
| `release` | Everything required to assemble/release locally. Live GitHub Project IDs, PostHog, and VPS stay `ACTIVATION_REQUIRED` rather than false `FAIL`.  |
| `ci-host` | VPS runtime requirements from an injectable facts fixture (`summarize_health`). Doctor never SSH. Missing runner/token is `ACTIVATION_REQUIRED`. |

## Checks

| Check                         | Typical repair / activation                                                                                                                                                                                                        |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python`                      | Install Python 3.11+ (`tomllib`).                                                                                                                                                                                                  |
| `git`                         | Install git and put it on `PATH`.                                                                                                                                                                                                  |
| `gh`                          | `brew install gh` then `gh auth login`. Activation, not a local-release failure.                                                                                                                                                   |
| `canonical-core`              | `scripts/nexus validate`                                                                                                                                                                                                           |
| `generated-drift`             | `scripts/nexus build`                                                                                                                                                                                                              |
| `claude` / `cursor` / `codex` | Missing `dist/` adapters: `WARN` on local/ci-host, `FAIL` on release. Repair: `scripts/nexus build`. User-home install is cutover (`ACTIVATION_REQUIRED`); do not overwrite `~/.claude` / `~/.cursor` / `~/.codex` without backup. |
| `task-state`                  | `chmod u+w` on `.nexus/tasks` or `NEXUS_RUNTIME_HOME`.                                                                                                                                                                             |
| `memory`                      | Restore `core/memory/retrieval-policy.toml`; `python3 -m nexus_harness.memory.cli doctor` if `.nexus/memory` exists.                                                                                                               |
| `project-registry`            | Fix `projects.toml`.                                                                                                                                                                                                               |
| `quality-tooling`             | Only when `--project` requires Biome/Vitest: `pnpm add -D @biomejs/biome vitest`. Otherwise `SKIP`.                                                                                                                                |
| `frontend-tooling`            | Only when the selected project requires Playwright. Otherwise `SKIP`.                                                                                                                                                              |
| `trivy`                       | Only when the selected project requires Trivy. Otherwise `SKIP`.                                                                                                                                                                   |
| `ci-profile`                  | Feed CI-host facts; do not SSH. See `docs/operations/ci-budget.md` and `infra/ci-vps/nexus-ci-host-doctor.sh`.                                                                                                                     |
| `github`                      | Set `NEXUS_GITHUB_PROJECT_ID` in user configuration (`core/project/project-fields.toml` keeps field names only).                                                                                                                   |
| `posthog`                     | `core/observability/posthog.toml` plus `POSTHOG_PERSONAL_API_KEY` in the environment. Never commit the key. Serialized via `safe_dict` / `dumps_report`.                                                                           |
| `release`                     | Assemble the v4 release (Task 5). Until then: `ACTIVATION_REQUIRED`.                                                                                                                                                               |

Plan 8: live VPS, live GitHub Project IDs, and unconfigured PostHog are `ACTIVATION_REQUIRED` or `SKIP` by profile. They must not make local release doctor fail.
