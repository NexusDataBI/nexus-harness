# Migration Map — v3 → Nexus Harness v4

## Preserve as canonical or upstream

| Current area | v4 destination |
|---|---|
| `nexus-frontend` | `skills/nexus-frontend` |
| `visual-validation` | retained routed frontend specialist/reference |
| `design-motion-principles` | retained locked upstream source |
| `fixing-motion-performance` | retained routed specialist |
| `vercel-react-best-practices` | retained locked upstream source |
| `vercel-composition-patterns` | retained locked upstream source |
| `feature-sliced-design` | retained routed specialist |
| `ui-craft-dense-dashboard` | retained routed specialist |
| `design-system`, `brand`, `extract-design-system`, `variant` | retained focused frontend sources |
| Superpowers engineering skills | retained as upstream primitives |
| Matt Pocock skills | retained as optional discovery/research primitives |

## Merge into Nexus lifecycle

| Current entrypoints | v4 owner |
|---|---|
| `tdd`, `tdd-workflow` | Superpowers TDD primitive invoked by `nexus-workflow` |
| `diagnosing-bugs`, `root-cause-tracing` | systematic-debugging primitive + `root-cause-analyst` |
| `verification-loop` | `nexus-verify` + Quality Gate |
| `code-review`, `source-command-review` | fresh reviewer agents + Stage 7 |
| `source-command-plan` | Stage 3 |
| source branch/commit/push/PR commands | `nexus-ship` |
| `handoff` | `nexus-handoff` |
| planner/architect lifecycle overlap | Stage 3 roles, not alternate spine |

## Merge frontend broad entrypoints

| Current entrypoints | v4 destination |
|---|---|
| `frontend-redesign-orchestrator` | `nexus-frontend` redesign mode |
| `design-taste-frontend` | unique heuristics routed from `nexus-frontend` |
| `baseline-ui`, `better-ui`, `better-interface` | polish/audit references |
| `better-layout`, `better-typography`, `better-colors` | focused design-system/brand references |
| `ui-styling`, `ui-ux-pro-max` | remove as broad competing entrypoints after unique-content extraction |
| `interface-review` | audit mode |
| `web-design-guidelines` | reference checklist |
| `explain-interface` | explain mode |
| `better-accessibility`, `fixing-accessibility` | `accessibility` |

## Remove from global configuration

- Hardcoded model routing.
- Project-specific client rules.
- VPS IP/SSH commands.
- Absolute project directories.
- Acelera/client automatic deployment rules.
- Claude environment variables inside Codex configuration.
- Disabled Cursor sandbox.
- Global allow-everything command policy.
- Mandatory Matt seven-phase lifecycle.
- Compaction that duplicates constitution instead of restoring structured task state.
- Bidirectional/blocked `harness-sync`.

## Delete only after evidence

- AppleDouble `._*`.
- `.bak` and stale caches/logs.
- Byte-identical skill/runtime copies after canonical source exists.
- Divergent overlapping skills only after unique guidance has been extracted and the migration ledger marks the decision resolved.

The source export itself is never deleted or modified by migration.
