# Nexus Harness v4

Canonical engineering harness for Claude Code, Cursor and Codex.

This repository is the **Canonical Source of Truth**. Runtime trees under `dist/` are generated and must never be edited by hand.

## Status

Plan 1 — Canonical Core & Migration is in progress. Later plans (workflow, adapters, CI, GitHub, frontend QA, PostHog, release) are not started.

## Layout

| Path                | Role                                               |
| ------------------- | -------------------------------------------------- |
| `inputs/`           | Immutable source archives and hashes               |
| `legacy/v3-export/` | Extracted v3 tree (read-only input, not canonical) |
| `core/`             | Canonical policies, workflow, quality, security    |
| `skills/`           | Canonical Nexus skills                             |
| `upstream/`         | Locked third-party sources                         |
| `dist/`             | Generated adapters (never source of truth)         |
| `docs/superpowers/` | Approved spec and implementation plans             |

## Authority

1. Explicit user instruction
2. Safety/security
3. `docs/superpowers/specs/nexus-harness-v4-final-design.md`
4. The plan currently in execution
5. Recorded rulings
6. Legacy behavior

If legacy contradicts the spec, the spec wins.

## Setup

```bash
tar -xzf inputs/nexus-harness-export-20260825-094238.tar.gz -C legacy
# flatten to legacy/v3-export if the archive has a top-level directory
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v
scripts/validate
```

## Do not

- Modify `inputs/*.tar.gz` or `inputs/*.zip`
- Treat `legacy/` or `dist/` as canonical source
- Push, open PRs, deploy, or change production without explicit approval
