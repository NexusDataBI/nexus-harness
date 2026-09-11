# Design direction

A good frontend direction is specific to the product and restrained enough to remain coherent.

## Direction pass

For new/replacement visual worlds, turn the Design Read into a compact direction before code:

1. **Palette roles** — background, surface, text, muted, accent, status; use actual project tokens/values when known.
2. **Typography roles** — body, display/heading, data/labels; choose for audience/content, not novelty.
3. **Layout concept** — describe information rhythm/alignment and the dominant spatial idea.
4. **Memorable move** — one characteristic visual or interaction idea.
5. **Restraint rule** — what stays quiet so the memorable move can carry the identity.
6. **State language** — loading, empty, error, disabled, success, focus.
7. **Copy vocabulary** — stable user-facing action names and tone.

## Anti-default review

Before implementation:

- Could this direction be reused for an unrelated product with only copy changes?
- Is any decision justified only as “modern,” “clean,” “premium,” or “AI-like”?
- Are cards, borders, labels, numbers, gradients, mono text, or motion encoding information, or merely filling space?
- Did an anti-slop rule accidentally become a new house style?

If yes, revise the direction.

## Refinement vs redesign

**Refinement:** keep identity, behavior, copy, and out-of-scope surfaces. Improve hierarchy, spacing, typography, states, accessibility, or craft.

**Redesign:** preserve product truth and constraints, but explicitly approve a replacement visual world before implementation. Do not blend the discarded world with the replacement by accident.

## Craft floor

Regardless of style, final work must handle responsive layout, keyboard focus, reduced motion, readable contrast, real interaction states, and runtime/browser health. Visual quality does not excuse broken product behavior.
