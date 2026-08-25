# Unique heuristics — Task 4 extraction status

Canonical skills absorbed the unique lifecycle, a11y, and frontend-routing guidance. Remaining extract work (do not delete export sources until these are resolved).

## Superpowers vs vendor-lock

Superpowers **are** in `upstream/vendor-lock.json` (`id: superpowers`, `canonical_path: upstream/superpowers`). The import is **partial**: only TDD, systematic-debugging, and subagent-driven-development (SDD) existed in the v3 export. No fake upstream copies were invented for the rest.

`nexus-workflow` names Superpowers primitives that were **not** in the v3 export and must be loaded from the host runtime until a later plan imports them:

- `brainstorming`
- `writing-plans`
- `using-git-worktrees`
- `verification-before-completion`
- `requesting-code-review`
- `receiving-code-review`
- `finishing-a-development-branch`

## Pending extract

| Source                                                                                                                                                           | Relationship         | Status                                                                                    |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------- |
| `better-accessibility` reference files (`semantics-and-aria.md`, `focus-and-keyboard.md`, `forms.md`, `hit-areas.md`, `motion-and-zoom.md`, `screen-readers.md`) | exact_duplicate      | Pending: optional references under `skills/accessibility/`                                |
| `ui-styling`                                                                                                                                                     | exact_duplicate      | Pending extract into `nexus-frontend` implement/design-system; listed in that skill       |
| `ui-ux-pro-max`                                                                                                                                                  | divergent (3 hashes) | Pending extract of unique search/explore heuristics; listed in `nexus-frontend`           |
| `implement` Claude vs Codex                                                                                                                                      | divergent            | Pending extract into `upstream/matt-pocock/implement`; Claude copy imported               |
| `code-review` Claude vs Codex                                                                                                                                    | divergent            | Two-axis + smell baseline in `nexus-quality`; tracker-setup prose pending reviewer agents |
| `tdd-workflow`                                                                                                                                                   | divergent            | Runner/plan-as-data glue in `nexus-workflow`; TDD loop stays Superpowers                  |
| `root-cause-tracing`                                                                                                                                             | divergent            | Pending `agents/root-cause-analyst.md` (not this task)                                    |
| `napkin`                                                                                                                                                         | divergent            | Reference only; not a canonical skill                                                     |
