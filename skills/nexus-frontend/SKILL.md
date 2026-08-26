---
name: nexus-frontend
description: "Single frontend entry skill. Mode router: implement, redesign, audit, explain, visual-validate, design-system, polish. Routes specialists; does not replace them."
---

# nexus-frontend

Single frontend entrypoint. Routes to locked upstream specialists. Does not copy Motion Principles, Vercel React guidance, or Impeccable into this file.

Authority order, load budget, and retained specialists: [references/router.md](references/router.md).

## Modes

Choose **one** primary mode:

| Mode              | Use when                                        | Routes                                                                     |
| ----------------- | ----------------------------------------------- | -------------------------------------------------------------------------- |
| `implement`       | Build or change UI in an existing visual world  | source of truth + stack policy + one surface specialist                    |
| `redesign`        | Multi-surface or replacement visual world       | discover → audit → authority → implement → visual-validate                 |
| `audit`           | Focused interface critique                      | Impeccable critique / `visual-validation` / `accessibility` as appropriate |
| `explain`         | Explain how an interface works                  | nexus-frontend `explain` mode                                              |
| `visual-validate` | Material visual change needs vision-in-the-loop | `visual-validation`                                                        |
| `design-system`   | Tokens, components, extraction, variants        | `design-system`, `brand`, `extract-design-system`, `variant`               |
| `polish`          | Craft pass after direction exists               | Impeccable; `baseline-ui` / `better-*` as focused references               |

## Source of truth (precedence)

1. explicit user request
2. project design system / brand
3. explicit Figma or visual target
4. surface specialist
5. framework engineering guidance
6. polish/generic guidance

Never silently override project brand or an explicit visual target. Details in [references/router.md](references/router.md).

## Surface class (implement / redesign)

`marketing` | `product` | `data-dense` | `motion` | `figma` | `architecture` | `validation`

Load budget: 1 source of truth + 1 surface specialist + 0–1 technical specialist + `visual-validation` at the end of material visual work. Do not load multiple generic visual specialists without a concrete reason.

- **marketing:** Impeccable critique/craft plus `design-motion-principles` or `vercel-react-best-practices` as appropriate. Anti-slop heuristic: declare a one-line Design Read before generating; do not default to AI-purple / three-card heroes / Inter+slate. Deny `ui-craft-dense-dashboard`.
- **data-dense:** `ui-craft-dense-dashboard`. Deny Taste.
- **motion:** `design-motion-principles` owns decisions; `fixing-motion-performance` and `accessibility` afterward when quality requires it. Do not copy motion recipes here.
- **React/Next:** `vercel-react-best-practices`, `vercel-composition-patterns`. Vercel skills are engineering guidance, never a hosting target. `feature-sliced-design` only for large architecture — not landings or small apps.
- **Figma:** source of truth when explicitly provided.
- **reference site:** `extract-design-system` is evidence, never the project DS.

Taste and Dense Dashboard are mutually exclusive by surface.

## Redesign phases (unique from frontend-redesign-orchestrator)

1. **Discover** — classify preserve / refresh / rebuild; record what must not change (flows, URLs, field names, legal copy).
2. **Audit** — smallest relevant set, not every specialist.
3. **Select authority** — document primary vs advisory.
4. **Implement** — this skill's policy + Vercel specialists by name.
5. **Validate** — `visual-validation`; ≤ two automatic correction passes.

## Implementation policy

- Inspect the existing stack before changing dependencies.
- Reuse project components/tokens before creating new ones.
- Honor the project's TypeScript / Tailwind / shadcn / Expo choices; do not impose shadcn on a repo that does not use it.
- Real loading, empty, error, and disabled states when the flow needs them.
- User-facing copy follows the project language.
- Do not redesign during a narrow bugfix.
- Retired local skills must not be invoked: `ux-audit`, `ux-writing`, `frontend-architecture-review`, `design-system-engineer`, `saas-product-review`.

## Visual-in-the-loop (material visual changes)

```text
start/reuse localhost → baseline screenshot when relevant → implement
→ interaction → desktop/mobile screenshots → console/network
→ visual reviewer → fix → screenshot again
```

Visual evidence is stale after relevant UI changes. A compile is not completion.

## Motion policy (Nexus, not a copy of Motion Principles)

Animate only when motion improves comprehension. Skeletons only when content shape is predictable. Respect `prefers-reduced-motion`. Avoid decorative hover-scale/stagger. Review loading, empty, error, and transition states. Details live in `design-motion-principles`.

## Accessibility

Route `accessibility` for a11y-bearing work. Do not duplicate that skill here. Optional recipes: `skills/accessibility/references/`.

## Frontend heuristic slice

`ui-styling` stack-honor policy lives in Implementation policy and [references/router.md](references/router.md); the encyclopedia stays in the export. `ui-ux-pro-max` search/explore rules live in the router; catalogs stay in the export. See `docs/migration/unique-heuristics.md`.
