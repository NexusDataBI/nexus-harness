# Frontend router

Authority, phase budgets, and specialist routing for `nexus-frontend`.

## Authority order

Higher wins:

1. explicit user request
2. project design system / brand
3. explicit Figma or visual target
4. approved Design Read / surface contract
5. surface specialist
6. framework engineering guidance
7. generic/search intelligence and polish

Never silently override a higher authority. Search catalogs and generic design intelligence live at level 7 only.

## Two-axis classification

Classify both:

- **intent:** `persuade | operate | read | experience`
- **surface:** `marketing | product | data-dense | motion | figma | architecture | validation`

Intent is the visitor/user outcome. Surface is the UI shape. The same product may have different intents on different routes.

Examples:

| Surface | Intent | Why |
| --- | --- | --- |
| SaaS landing page | persuade | visitor decides/acts |
| SaaS dashboard | operate | user completes work |
| product docs | read | user understands |
| portfolio gallery | experience | artifact is the experience |

## Phase load budget

Budget applies **per phase**:

| Phase | Budget |
| --- | --- |
| discover/authority | 1 source of truth |
| direction/intelligence | 1 owning visual specialist + optional advisory query |
| implementation | 1 stack/engineering specialist |
| harden/audit | 1 focused specialist per concrete risk |
| validation | `visual-validation`; add accessibility only for a11y-bearing findings |
| polish | 1 craft specialist after direction exists |

Do not load multiple generic visual specialists without a concrete reason. Direction specialists are mutually exclusive owners for a pass.

## Specialist roles

| Specialist | Role | Authority |
| --- | --- | --- |
| `frontend-design` | distinctive direction for new/replacement visual worlds when host runtime exposes it | owns direction only when selected |
| Impeccable | shape/new-work, critique, harden, polish | owns selected craft pass |
| `ui-ux-pro-max` | searchable design/UX intelligence when available | advisory only |
| `ui-craft-dense-dashboard` | dense operational/dashboard craft | owns data-dense surface craft |
| `design-motion-principles` | motion decisions | owns motion |
| `fixing-motion-performance` | diagnose motion performance | technical follow-up |
| `accessibility` | keyboard/name/focus/forms/motion/WCAG-bearing work | owns a11y |
| `vercel-react-best-practices` | React/Next performance/implementation | engineering only |
| `vercel-composition-patterns` | component APIs/composition | engineering only |
| `visual-validation` | rendered browser/device evidence | validation only |
| official Figma skills | canvas/file operations | Figma execution only |

Vercel guidance never implies Vercel hosting. Optional host specialists do not become hard dependencies.

## Direction routing

Use `frontend-design` or Impeccable as the direction owner when a new/replacement visual world needs stronger aesthetic authorship. Do not run both as competing directors in the same direction pass.

Use `ui-ux-pro-max` only as a bounded query layer:

1. ask for one semantic outcome or one design-system direction;
2. keep one dominant intent and 2–5 useful terms;
3. verify product/platform fit;
4. retry once if off-topic;
5. never persist or present unverified output as project truth.

If it is unavailable, proceed using the Design Read and existing evidence.

## Surface routing

- **marketing / persuade:** direction specialist first; optional motion or React guidance later. Deny dense-dashboard defaults.
- **product / operate:** incumbent design system first; Impeccable or project patterns for craft; stack specialist for implementation.
- **data-dense / operate:** `ui-craft-dense-dashboard`; prioritize scanability, hierarchy, comparison, and compact states.
- **read:** typography, structure, navigation, and comprehension outrank novelty.
- **experience:** artifact/subject leads; chrome recedes; motion only when it supports the experience.
- **motion:** `design-motion-principles`; accessibility/performance follow as needed.
- **figma design-to-code:** provided Figma file is visual truth.
- **figma code-to-figma:** follow `code-to-figma.md`.
- **validation:** `visual-validation`, plus `accessibility` only when the finding is a11y-bearing.
- **architecture:** framework/component architecture guidance must not silently redesign the surface.

## Preserve vs replace

- `implement` and narrow `polish` preserve the incumbent visual identity unless scope explicitly says otherwise.
- `redesign` may replace the visual world, but keeps product truth, content constraints, flows, and native/platform affordances.
- Missing a design-system file is not evidence that the project is greenfield. Inspect incumbent tokens, CSS, components, screenshots, and assets.

## Stack policy

Detect the stack from the repository. Honor existing TypeScript/Tailwind/shadcn/Expo conventions. Do not run `shadcn init` or introduce a design framework unless the repository already uses it or the user explicitly requests it.
