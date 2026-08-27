# Nexus v4 rollback

Use this runbook when a cutover or activation step fails. Do not delete the v3 backup. Pair with [cutover.md](cutover.md) and [activation.md](activation.md).

## Immediate triggers

Roll back **now** (do not continue to the next runtime or live step) if any of the following occur:

1. Runtime startup failure (Codex, Cursor, or Claude will not start with the new tree).
2. Repeated hook block without an actionable reason (doctor/hook output has no `repair` / `activate` line).
3. Inability to parse generated settings (`dist/claude/settings.json`, `dist/cursor/sandbox.json`, `dist/codex/config.toml`, or the copies under the install target).
4. Missing project access (`projects.toml` unreadable, or `scripts/nexus project show --id <project-id>` fails).
5. Completion-gate false positives in smoke (`scripts/nexus evals run` disagrees with `tests/test_completion.py` / `evals/cases/ambiguous-task.json` — a task reported done while the gate should still `FAIL`).

Doctor `ACTIVATION_REQUIRED` for GitHub, PostHog, or CI-host is **not** a rollback trigger. Those wait for [activation.md](activation.md). Doctor `FAIL` is a rollback trigger.

## Restore the last atomic install

`scripts/nexus install SOURCE TARGET` (and `scripts/install SOURCE TARGET`) prints the sibling backup created by `atomic_install` in `src/nexus_harness/install.py`. Restore with `rollback_install`:

```bash
: "${INSTALL_BACKUP:?path printed by scripts/nexus install}"
: "${INSTALL_TARGET:?the target directory that install replaced}"
PYTHONPATH=src python3 -m nexus_harness.install diff "$INSTALL_TARGET" harness.lock || true
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
import os
from nexus_harness.install import rollback_install, tree_digests

backup = Path(os.environ["INSTALL_BACKUP"])
target = Path(os.environ["INSTALL_TARGET"])
displaced = rollback_install(backup, target)
print(displaced)
print("restored files", len(tree_digests(target)))
PY
```

`rollback_install` is a sibling `os.replace`: it displaces the failed tree and puts the backup back. Confirm parse after restore:

```bash
python3 -c "import json, pathlib; p=pathlib.Path('$INSTALL_TARGET');
print('ok', any((p/'claude'/'settings.json').is_file() for _ in [0]))"
scripts/nexus doctor --profile local
```

## Restore the v3 timestamped archive

If sibling install backups are missing or the operator wants the pre-cutover homes, use the read-only v3 archive from `NEXUS_BACKUP_ROOT` (see [cutover.md](cutover.md)). Copy it to a writable restore workspace first — do not mutate the retained archive.

```bash
: "${NEXUS_BACKUP_ROOT:?}"
: "${V3_BACKUP:?timestamped nexus-v3-* directory}"
RESTORE="$(mktemp -d)"
cp -R "$V3_BACKUP" "$RESTORE/v3"
chmod -R u+w "$RESTORE/v3"

# Example: restore a home tarball into a disposable directory, not blindly onto $HOME
mkdir -p "$RESTORE/homes"
if [ -f "$RESTORE/v3/homes/.claude.tar.gz" ]; then
  tar -C "$RESTORE/homes" -xzf "$RESTORE/v3/homes/.claude.tar.gz"
fi
```

Live `$HOME/.claude` / `$HOME/.cursor` / `$HOME/.codex` restore requires the same approval as cutover. Prefer restoring into disposable targets, then `scripts/nexus install` only after parse + `scripts/nexus doctor --profile local`.

## v3 backup retention

Do **not** delete the v3 backup after cutover.

1. After a successful cutover step, `chmod -R a-w` the timestamped `nexus-v3-*` directory so it stays read-only.
2. Retain it until at least one successful real task has completed through **each** of Claude, Cursor, and Codex under v4.
3. Only then may the operator archive it elsewhere. Deleting it before that point is not allowed.

`tests/test_install.py` covers disposable-home install/rollback; it does not replace this operator runbook.
