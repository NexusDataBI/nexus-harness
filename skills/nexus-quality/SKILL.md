---
name: nexus-quality
description: "Quality profiles, ratchet, and reviewer selection for Nexus Stage 6–7. Use when choosing the quality bar, interpreting metrics, or dispatching fresh reviewers."
---

# nexus-quality

Owns **profiles, ratchet, and reviewer selection**. Does not collect evidence (`nexus-verify`) and does not ship (`nexus-ship`).

Never weaken policy or baseline to make a change pass.

## Profiles

From `core/quality/profiles.toml`. Stage 0 records which profile applies.

| Profile    | Format/lint | Unit | Coverage | E2E/visual | Security | Extra                                           |
| ---------- | ----------- | ---- | -------- | ---------- | -------- | ----------------------------------------------- |
| `light`    | yes         | yes  | no       | no         | no       |                                                 |
| `standard` | yes         | yes  | yes      | no         | yes      | typecheck when configured                       |
| `strict`   | yes         | yes  | yes      | yes        | yes      | typecheck + fresh review                        |
| `critical` | yes         | yes  | yes      | yes        | yes      | typecheck + fresh review + production approvals |

Default JS/TS checks (when the graph says they apply): Biome, Vitest unit/integration/coverage, Playwright when browser behavior is affected, Trivy as appropriate, project build/typecheck when configured, Quality Ratchet.

## Ratchet

From `core/quality/ratchet.toml`:

| Mode       | Meaning                            |
| ---------- | ---------------------------------- |
| `absolute` | must satisfy a fixed condition     |
| `ratchet`  | maintain or improve; never regress |
| `budget`   | tolerance for noisy metrics        |

Defaults: build/type errors and failing tests are `absolute`; critical security is `absolute`; coverage and lint warnings are `ratchet`; performance is `budget`. Required-metric failure overrides an aggregate PASS. Promote improvements in the same PR; never lower the bar.

## Reviewer selection

Fresh review (Stage 7) uses spec/Issue/acceptance + diff + evidence. Activate specialists by **domain and risk**, not by model identity:

| Trigger                                  | Reviewer                                 |
| ---------------------------------------- | ---------------------------------------- |
| any code-changing PR                     | `code-reviewer` (Standards + Spec axes)  |
| auth, secrets, user input, webhooks, PII | `security-reviewer` (mandatory)          |
| SQL, migration, schema                   | `database-reviewer` (mandatory)          |
| frontend visual change                   | `nexus-frontend` audit / visual-validate |
| accessibility-bearing UI                 | `accessibility`                          |
| confirmed high/blocker                   | blocks completion                        |

`blocker` and `high` confirmed findings block Done. Review may `SKIP` only with a recorded justification.

## Two-axis review (unique from code-review)

Pin a fixed point (`git diff <fixed-point>...HEAD`). Run **Standards** and **Spec** as separate fresh contexts, then aggregate.

- **Standards:** repo coding standards win; Fowler smells are labelled heuristics, never hard violations when tooling already enforces them.
- **Spec:** originating Issue / PRD / spec. If none exists, report "no spec available" instead of inventing one.

Do not paste Superpowers review playbooks here. Invoke `requesting-code-review` / `receiving-code-review` when that is the mechanism.

## Smell baseline (heuristics, repo overrides)

Mysterious Name, Duplicated Code, Feature Envy, Data Clumps, Primitive Obsession, Repeated Switches, Shotgun Surgery, Divergent Change, Speculative Generality, Message Chains, Middle Man, Refused Bequest.

## Tooling policy

One primary tool per responsibility. Prefer existing, free, open-source, local. A new external service needs uncovered capability, material benefit, evidence existing tools cannot cover it, and explicit approval.

Unique Nexus gates above are canonical. Divergent Claude vs Codex `code-review` copies remain in the immutable export; tracker-setup prose is not a second review product.
