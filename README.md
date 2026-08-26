# Nexus Harness v4

Canonical engineering harness for Claude Code, Cursor and Codex.

This repository is the **Canonical Source of Truth**. Runtime trees under `dist/` are generated and must never be edited by hand.

## Status

Plans 1–4 are implemented. `dist/` is generated-only; verification hashes expected artifacts from canonical sources.

Operational TaskState lives outside the git worktree (`NEXUS_RUNTIME_HOME` or `~/.nexus-harness/runtime/<repo-id>/<task-id>/`). Project memory remains under `<repo>/.nexus/memory`.

## Layout

| Path                | Role                                               |
| ------------------- | -------------------------------------------------- |
| `inputs/`           | Immutable source archives and hashes               |
| `legacy/v3-export/` | Extracted v3 tree (read-only input, not canonical) |
| `core/`             | Canonical policies, workflow, quality, security    |
| `skills/`           | Canonical Nexus skills                             |
| `upstream/`         | Locked third-party sources                         |
| `dist/`             | Generated adapters + packaged hook engine          |
| `docs/superpowers/` | Approved spec and implementation plans             |

## Authority

1. Explicit user instruction
2. Safety/security
3. `docs/superpowers/specs/nexus-harness-v4-final-design.md`
4. The plan currently in execution
5. Recorded rulings
6. Legacy behavior

If legacy contradicts the spec, the spec wins.

## Canonical verification (fresh checkout)

`dist/` is generated and gitignored. `harness.lock` records **expected** generated hashes computed from canonical sources (`render_all()`, `src/nexus_harness`, `core/`). Validation does **not** require a previously materialized `dist/`.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v
scripts/validate
git diff --check
PYTHONPATH=src python3 -m compileall -q src
```

## Setup / install

```bash
tar -xzf inputs/nexus-harness-export-20260825-094238.tar.gz -C legacy
# flatten to legacy/v3-export if the archive has a top-level directory
```

`scripts/compile` materializes `render_all()` into `dist/`, copies the Python hook engine to `dist/src/nexus_harness`, copies `core/`, and refreshes `harness.lock`. Use it when installing a runtime tree — not as a prerequisite for the verification sequence above.

Install a compiled tree locally (never to a global runtime without approval):

```bash
scripts/install dist /tmp/nexus-harness-runtime
```

Lifecycle events from any CWD:

```bash
python3 /tmp/nexus-harness-runtime/hooks/nexus_event.py --event SessionStart < payload.json
```

Claude uses `hooks/claude_event.py` (same engine, Claude transport). Cursor and Codex invoke `python3 hooks/nexus_event.py --event <EventName>` with JSON on stdin.

## Do not

- Modify `inputs/*.tar.gz` or `inputs/*.zip`
- Treat `legacy/` or `dist/` as canonical source
- Persist TaskState or memory candidates inside the repository `.nexus/`
- Push, open PRs, deploy, or change production without explicit approval
