---
name: nexus-frontend
description: Use when frontend work changes, redesigns, audits, validates, explains, or extracts a user-facing interface, design system, visual target, or code-to-Figma flow.
---

# nexus-frontend

Single frontend entrypoint and authority router. It chooses the visual contract and smallest specialist set; specialist playbooks stay in their own skills.

Read routing details in [references/router.md](references/router.md).

## Modes

Choose **one** primary mode:

| Mode | Use when |
| --- | --- |
| `implement` | Change UI inside an existing visual world |
| `redesign` | Replace/materially reshape a visual world |
| `audit` | Critique without redesigning by default |
| `explain` | Explain how an interface works |
| `visual-validate` | Material visual work needs rendered evidence |
| `design-system` | Tokens/components/variants/extraction |
| `polish` | Direction exists; improve craft |
| `code-to-figma` | Codebase → editable Figma model → QA |

## Authority

Higher authority wins:

1. explicit user request
2. project design system / brand
3. explicit Figma or visual target
4. approved Design Read / surface contract
5. surface specialist
6. framework engineering guidance
7. generic/search intelligence and polish

A catalog or specialist never silently overrides project truth.

## Surface contract

For material frontend work classify both:

```text
intent: persuade | operate | read | experience
surface: marketing | product | data-dense | motion | figma | architecture | validation
platform: detected/declared
stack: detected from repository
```

Intent describes user success; surface selects the specialist. Do not infer style from product category. See [references/surface-intent.md](references/surface-intent.md).

## Design Read

A new surface, redesign, or material visual-direction change requires a compact Design Read **before implementation**:

```text
subject · audience/context · primary_job · intent/surface
authority · visual_pov · memorable_move
variance/motion/density (1–10) · preserve · avoid
```

A narrow bugfix/refinement preserves the incumbent visual world and does not invent a new direction.

The read must pass one check: if the same direction fits an unrelated product after changing only the name/copy, revise it.

See [references/design-read.md](references/design-read.md) and [references/design-direction.md](references/design-direction.md).

## Phase-scoped specialists

Specialists participate by phase, not as a committee:

```text
discover/authority
→ direction/intelligence
→ implementation
→ harden/audit
→ visual validation
→ optional polish
```

Per phase: 1 source of truth + 1 owning specialist + 0–1 technical specialist.

- `frontend-design` may own distinctive direction for a new/replacement world when the host exposes it.
- Impeccable may own shape/new-work, critique, harden, or polish; do not make it compete with another direction owner in the same pass.
- `ui-ux-pro-max` may provide bounded search/intelligence when available; it is **advisory only**.
- `ui-craft-dense-dashboard` owns dense operational craft.
- `design-motion-principles` owns motion decisions.
- `vercel-react-best-practices` / `vercel-composition-patterns` are implementation guidance, never visual authority or hosting requirements.
- `accessibility` owns a11y-bearing work.
- `visual-validation` owns rendered QA.

Optional host specialists are never hard dependencies. If unavailable, continue from project authority + Design Read.

## Implementation policy

Inspect the stack first; reuse project components/tokens; do not impose shadcn or redesign during a narrow bugfix. Preserve product truth, flows, URLs, field names, legal/factual copy unless scope changes them. Implement real loading, empty, error, disabled, focus, and success states when relevant.

Refinement preserves identity. Redesign may replace visual identity only after direction approval.

## Anti-slop

**Never replace one default aesthetic with another default aesthetic.**

Every material visual decision needs a reason tied to subject, audience, and primary job. “Modern,” “clean,” or “premium” alone is not a design rationale. Prefer one memorable move with disciplined supporting UI.

## Visual completion

Material visual changes require current browser/device evidence:

```text
baseline when relevant → implement → exercise states/interactions
→ representative screenshots → console/network
→ visual reviewer → batch fixes → confirmation
```

Relevant UI changes stale prior visual evidence. A compile is not visual completion. Motion remains governed by [references/motion-policy.md](references/motion-policy.md), including reduced-motion requirements.

