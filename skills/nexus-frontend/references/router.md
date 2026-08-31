# Frontend router

Authority, load budget, and specialist routing for `nexus-frontend`.
Do not copy Motion Principles, Impeccable, or Vercel guidance into this file.

## Authority order

Higher wins. Do not invert this list for convenience.

1. explicit user request
2. project design system / brand
3. explicit Figma or visual target
4. surface specialist
5. framework engineering guidance
6. polish/generic guidance

Never silently override project brand or an explicit visual target.
Search catalogs and generic design intelligence live at level 6 only.
Their recommendations never outrank an explicit request, brand, or Figma target.

## Load budget

Per phase: 1 source of truth + 1 surface specialist + 0–1 technical specialist + `visual-validation` at the end of material visual work.

Do not load multiple generic visual specialists without a concrete reason.
Taste-class guidance and dense-dashboard guidance are mutually exclusive by surface.

## Retained specialists

Route these by name. Do not duplicate their text into runtime roots.

| Specialist                    | When                                              |
| ----------------------------- | ------------------------------------------------- |
| `design-motion-principles`    | Motion is a decision, not decoration              |
| `visual-validation`           | Material visual change needs vision-in-the-loop   |
| Impeccable                    | Critique, craft, or polish after direction exists |
| `accessibility`               | Keyboard, name, focus, form, motion, or WCAG work |
| `vercel-react-best-practices` | React/Next performance and implementation         |
| `vercel-composition-patterns` | Component API and composition                     |

Vercel skills are engineering guidance, never a hosting target.
Optional a11y recipes live under `skills/accessibility/references/`. Do not invent a second accessibility product.

## Surface routing

- **marketing:** Impeccable plus `design-motion-principles` or a Vercel specialist when the work needs it. Deny dense-dashboard.
- **data-dense:** `ui-craft-dense-dashboard`. Deny Taste-class specialists.
- **motion:** `design-motion-principles` owns decisions; `accessibility` afterward when quality requires it.
- **React/Next:** `vercel-react-best-practices`, `vercel-composition-patterns`. `feature-sliced-design` only for large architecture.
- **Figma (design-to-code):** the provided file is source of truth when the user named it.
- **Figma (code-to-figma):** orchestrate via [code-to-figma.md](code-to-figma.md). Official Figma skills execute canvas work.
- **validation:** `visual-validation` plus `accessibility` when the defect is a11y-bearing.

## Search / explore

When polish/generic guidance is used, keep one dominant intent and 2–5 terms.
Ask for the semantic outcome first, then the implementation stack.
Retry once; do not persist unverified catalog output.
Do not invoke the `ui-ux-pro-max` entrypoint or copy its datasets.

## Stack recipes

Honor the project's existing TypeScript / Tailwind / shadcn / Expo stack.
Do not impose shadcn, and do not run `shadcn init`, unless the repo already uses it or the user asks.
Do not copy the `ui-styling` encyclopedia or its scripts into this tree.
