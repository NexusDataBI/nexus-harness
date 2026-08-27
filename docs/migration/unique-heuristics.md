# Unique heuristics — Task 4 extraction status

Canonical skills absorbed the unique lifecycle, a11y, and frontend-routing guidance. Unresolved divergent decisions = 0. Export sources stay immutable until a later deletion plan; this document no longer blocks Plan 8.

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

## Evaluated — Plan 6 Task 1 (frontend slice)

| Source                                                                                                                                                           | Relationship         | Status                                                                                                                                                                                                                                                 |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `better-accessibility` reference files (`semantics-and-aria.md`, `focus-and-keyboard.md`, `forms.md`, `hit-areas.md`, `motion-and-zoom.md`, `screen-readers.md`) | exact_duplicate      | PRESERVED: copied to `skills/accessibility/references/`. Same a11y skill; no second a11y product. `agents/openai.yaml` not copied.                                                                                                                     |
| `ui-styling`                                                                                                                                                     | exact_duplicate      | ALREADY_COVERED: stack-honor / do-not-impose-shadcn policy in `skills/nexus-frontend` implement + `references/router.md`. Encyclopedia, CLI recipes, and scripts DISCARDED_WITH_REASON (generic shadcn/Tailwind docs; remain in the immutable export). |
| `ui-ux-pro-max`                                                                                                                                                  | divergent (3 hashes) | PRESERVED: search/explore contract and "recommendations never outrank brand/Figma/brief" in `skills/nexus-frontend/references/router.md`. Catalogs, scripts, and the three divergent entrypoints DISCARDED_WITH_REASON (export only).                  |

## Evaluated — Plan 8 debt gate (remaining extract)

| Source                        | Relationship | Status                                                                                                                                                                                                                                                                                               |
| ----------------------------- | ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `implement` Claude vs Codex   | divergent    | ALREADY_COVERED: Claude copy is canonical at `upstream/matt-pocock/implement` (Nexus no-auto-commit patch). Codex-only wording DISCARDED_WITH_REASON — adapters consume the same Matt skill; do not duplicate per runtime.                                                                           |
| `code-review` Claude vs Codex | divergent    | ALREADY_COVERED: two-axis review and Fowler smell baseline live in `skills/nexus-quality`. Tracker-setup prose DISCARDED_WITH_REASON — Issue tracking is Plan 5; Superpowers `requesting-code-review` / `receiving-code-review` load from the host runtime. Do not copy entire legacy review skills. |
| `tdd-workflow`                | divergent    | ALREADY_COVERED: runner detection, plan-as-data, and RED/GREEN evidence mapping live in `skills/nexus-workflow`. TDD loop vocabulary stays Superpowers `test-driven-development`.                                                                                                                    |
| `root-cause-tracing`          | divergent    | ALREADY_COVERED: "root-cause before patch" and failure-memory glue live in `skills/nexus-workflow` Stage 5. DISCARDED_WITH_REASON: do not invent `agents/root-cause-analyst.md` or missing Superpowers files; `systematic-debugging` is the imported primitive.                                      |
| `napkin`                      | divergent    | DISCARDED_WITH_REASON: operator local note / reference only, not a canonical v4 skill. Remains in the immutable export.                                                                                                                                                                              |
