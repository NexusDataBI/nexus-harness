# Nexus v4 cutover (v3 → v4)

Documentation only. Do not run this runbook until a passing v4 release exists, the current runtime config is backed up, and the operator has approved installation. Do not overwrite `$HOME/.claude`, `$HOME/.cursor`, or `$HOME/.codex` without that backup and approval.

Live GitHub Project IDs, VPS CI, and PostHog stay `ACTIVATION_REQUIRED` until [activation.md](activation.md). Rollback: [rollback.md](rollback.md). Doctor: [doctor.md](doctor.md).

## Preconditions

Work from the v4 tree (extracted `release/nexus-harness-v4/` or this checkout). Confirm:

```bash
scripts/validate
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
scripts/nexus evals run
scripts/nexus build adapters
scripts/diff
scripts/nexus doctor --profile release
```

`scripts/build` is the release assembler (`python3 -m nexus_harness.release`). `scripts/nexus build` / `scripts/compile` only materialize adapters into `dist/`. `scripts/install` and `scripts/nexus install` call `atomic_install` in `src/nexus_harness/install.py`: generated files replace as one directory rename; files not in the source tree are copied forward; a sibling rollback directory is always created. There is no silent overwrite.

`dist/` is compile output (gitignored except `dist/.gitkeep`). After compile, Codex/Cursor/Claude files match `tests/golden/` (`tests/golden/codex/config.toml`, `tests/golden/cursor/sandbox.json`, `tests/golden/claude/settings.json`).

## 1. Pre-cutover backup

Archive current Claude/Cursor/Codex user configuration and the current harness install into a timestamped directory **outside** the v4 release tree. Set `NEXUS_BACKUP_ROOT` first (never inside `release/` or the checkout).

```bash
: "${NEXUS_BACKUP_ROOT:?set NEXUS_BACKUP_ROOT outside the v4 release directory}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$NEXUS_BACKUP_ROOT/nexus-v3-$STAMP"
mkdir -p "$BACKUP/homes" "$BACKUP/harness"

for name in .claude .cursor .codex; do
  if [ -e "$HOME/$name" ]; then
    tar -C "$HOME" -czf "$BACKUP/homes/${name}.tar.gz" "$name"
  fi
done

if [ -n "${NEXUS_RUNTIME_HOME:-}" ] && [ -d "$NEXUS_RUNTIME_HOME" ]; then
  tar -C "$(dirname "$NEXUS_RUNTIME_HOME")" \
    -czf "$BACKUP/harness/runtime-home.tar.gz" \
    "$(basename "$NEXUS_RUNTIME_HOME")"
elif [ -d "$HOME/.nexus-harness" ]; then
  tar -C "$HOME" -czf "$BACKUP/harness/nexus-harness.tar.gz" .nexus-harness
fi

if [ -f harness.lock ]; then
  cp harness.lock "$BACKUP/harness.lock"
fi

printf '%s\n' "$BACKUP" > "$BACKUP/BACKUP_PATH.txt"
```

Do not delete this backup after cutover. After a successful install, mark it read-only (`chmod -R a-w`) and keep it until at least one successful real task has completed through each of Claude, Cursor, and Codex under v4. See [rollback.md](rollback.md).

## 2. Canonical core, then one runtime at a time

Install canonical Nexus core first. Then generated adapters one runtime at a time: **Codex first**, **Cursor second**, **Claude last** (Claude has the richest hooks: SessionStart, UserPromptSubmit, PreToolUse, TaskCompleted, PreCompact, PostCompact). Run `scripts/nexus doctor` after each runtime. Use disposable test-profile targets (`$CODEX_HOME`, `$CURSOR_HOME`, `$CLAUDE_HOME`) until smoke passes — not `$HOME/.claude` / `$HOME/.cursor` / `$HOME/.codex`.

```bash
: "${NEXUS_RUNTIME_HOME:?set NEXUS_RUNTIME_HOME to a writable test runtime home}"
: "${CODEX_HOME:?set CODEX_HOME to a disposable Codex test profile}"
: "${CURSOR_HOME:?set CURSOR_HOME to a disposable Cursor test profile}"
: "${CLAUDE_HOME:?set CLAUDE_HOME to a disposable Claude test profile}"
```

### 2.1 Canonical core

```bash
CORE_STAGE="$(mktemp -d)"
mkdir -p "$CORE_STAGE/src" "$CORE_STAGE/core" "$CORE_STAGE/hooks"
cp -R dist/src/nexus_harness "$CORE_STAGE/src/"
cp -R dist/core "$CORE_STAGE/core/"
cp dist/hooks/nexus_event.py "$CORE_STAGE/hooks/"
scripts/nexus install "$CORE_STAGE" "$NEXUS_RUNTIME_HOME"
scripts/nexus doctor --profile local
```

Record the backup path printed by `scripts/nexus install`. That sibling tree is the install-level rollback for this step.

### 2.2 Codex first (test profile)

Generated: `dist/AGENTS.md`, `dist/codex/config.toml`, `dist/hooks/nexus_event.py`.

```bash
CODEX_STAGE="$(mktemp -d)"
mkdir -p "$CODEX_STAGE/codex" "$CODEX_STAGE/hooks"
cp dist/AGENTS.md "$CODEX_STAGE/"
cp dist/codex/config.toml "$CODEX_STAGE/codex/"
cp dist/hooks/nexus_event.py "$CODEX_STAGE/hooks/"
scripts/nexus install "$CODEX_STAGE" "$CODEX_HOME"
python3 -c "import tomllib, pathlib; tomllib.loads(pathlib.Path('$CODEX_HOME/codex/config.toml').read_text())"
scripts/nexus doctor --profile local
scripts/nexus evals run
```

Stop and roll back this target if Codex cannot start, `config.toml` cannot be parsed, or `scripts/nexus doctor` gates `FAIL`.

### 2.3 Cursor second (test profile)

Generated: `dist/USER_RULES.md`, `dist/.cursor/rules/nexus-workflow.mdc`, `dist/cursor/sandbox.json`.

```bash
CURSOR_STAGE="$(mktemp -d)"
mkdir -p "$CURSOR_STAGE/.cursor/rules" "$CURSOR_STAGE/cursor" "$CURSOR_STAGE/hooks"
cp dist/USER_RULES.md "$CURSOR_STAGE/"
cp dist/.cursor/rules/nexus-workflow.mdc "$CURSOR_STAGE/.cursor/rules/"
cp dist/cursor/sandbox.json "$CURSOR_STAGE/cursor/"
cp dist/hooks/nexus_event.py "$CURSOR_STAGE/hooks/"
scripts/nexus install "$CURSOR_STAGE" "$CURSOR_HOME"
python3 -c "import json, pathlib; json.loads(pathlib.Path('$CURSOR_HOME/cursor/sandbox.json').read_text())"
scripts/nexus doctor --profile local
scripts/nexus evals run
```

`sandbox.json` must parse, `type` must be `workspace_readwrite`, and `disabled` must be absent.

### 2.4 Claude last (test profile)

Generated: `dist/claude/CLAUDE.md`, `dist/claude/settings.json`, `dist/hooks/claude_event.py`.

```bash
CLAUDE_STAGE="$(mktemp -d)"
mkdir -p "$CLAUDE_STAGE/claude" "$CLAUDE_STAGE/hooks"
cp dist/claude/CLAUDE.md "$CLAUDE_STAGE/claude/"
cp dist/claude/settings.json "$CLAUDE_STAGE/claude/"
cp dist/hooks/claude_event.py "$CLAUDE_STAGE/hooks/"
cp dist/hooks/nexus_event.py "$CLAUDE_STAGE/hooks/"
scripts/nexus install "$CLAUDE_STAGE" "$CLAUDE_HOME"
python3 -c "import json, pathlib; json.loads(pathlib.Path('$CLAUDE_HOME/claude/settings.json').read_text())"
scripts/nexus doctor --profile local
scripts/nexus doctor --profile release
scripts/nexus evals run
```

## 3. Rollback triggers (immediate)

Roll back the step that failed. Do not continue to the next runtime. See [rollback.md](rollback.md).

- Runtime startup failure
- Repeated hook block without an actionable reason
- Inability to parse generated settings (`settings.json`, `sandbox.json`, `config.toml`)
- Missing project access (`projects.toml` / `scripts/nexus project show --id <project-id>`)
- Completion-gate false positives in smoke (`scripts/nexus evals run`, especially `evals/cases/ambiguous-task.json` and unit coverage in `tests/test_completion.py`)

## 4. Live homes (mapping, not tree replace)

Do **not** `atomic_install` a generated staging tree onto `$HOME/.codex`, `$HOME/.cursor`, or `$HOME/.claude`. Those homes are shared runtime config (user + Nexus). Copy-forward of a 600 MB home is forbidden.

Two installation classes:

- **NEXUS-OWNED TREE** — Nexus controls the destination subtree. `atomic_install` is allowed. Default engine: `$HOME/.nexus-harness/install/<version>/`.
- **SHARED RUNTIME CONFIG** — structured merge only (`CREATE` / `MERGE` / `UPDATE_OWNED` / `PRESERVE` / `CONFLICT`). Fail closed on malformed JSON/TOML or duplicate owned blocks.

Plan mode has zero mutation:

```bash
scripts/nexus --json runtime install codex --plan
scripts/nexus --json runtime install cursor --plan --project /path/to/repo
scripts/nexus --json runtime install claude --plan
```

Apply one runtime at a time (Codex → Cursor → Claude) only when the plan has no `CONFLICT`:

```bash
scripts/nexus --json runtime install codex --apply
scripts/nexus doctor --profile local
```

Rollback shared files from the backup root printed by `--apply`:

```bash
scripts/nexus --json runtime rollback codex --backup "$BACKUP_ROOT"
```

Live mapping (this machine's discovery; do not assume other OS layouts):

| Runtime | Generated                          | Live destination                      | Class                                                                                  |
| ------- | ---------------------------------- | ------------------------------------- | -------------------------------------------------------------------------------------- |
| Codex   | `codex/config.toml`                | `~/.codex/config.toml`                | SHARED merge of `sandbox_mode` / `approval_policy`; never weaken a stricter user value |
| Codex   | `AGENTS.md`                        | `~/.codex/AGENTS.md`                  | SHARED owned block `NEXUS_HARNESS_BEGIN/END`                                           |
| Cursor  | `USER_RULES.md`                    | not `~/.cursor/USER_RULES.md`         | `NOT_APPLICABLE` (Cursor 3.x user rules are app settings)                              |
| Cursor  | `cursor/sandbox.json`              | not `~/.cursor/sandbox.json`          | `NEXUS_INTERNAL_ONLY`; Cursor CLI uses `cli-config.json` (`KEEP_EXTERNAL`)             |
| Cursor  | `.cursor/rules/nexus-workflow.mdc` | **project** `.cursor/rules/`          | `PROJECT_SUPPORTED`                                                                    |
| Claude  | `claude/CLAUDE.md`                 | `~/.claude/CLAUDE.md`                 | SHARED owned block                                                                     |
| Claude  | `claude/settings.json`             | `~/.claude/settings.json`             | SHARED hook merge; coexist with unrelated matchers; idempotent                         |
| Engine  | `hooks/*.py` + `src/` + `core/`    | `~/.nexus-harness/install/<version>/` | NEXUS-OWNED TREE                                                                       |

Canonical templates stay portable (`python3 hooks/claude_event.py ...`). Live apply rewrites Claude hook commands to the installed engine path. Do not embed machine-absolute paths in Canonical Core.

Keep the Phase A backup read-only. Do not treat doctor `ACTIVATION_REQUIRED` for GitHub / PostHog / CI-host as a cutover failure.
