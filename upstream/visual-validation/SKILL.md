---
name: visual-validation
description: "Browser-based visual validation and evidence gate for significant frontend changes. Use after UI implementation or redesign to verify responsive layout, interaction states, console/network health, keyboard/focus behavior and motion preferences with bounded correction passes."
---

# Visual Validation

## Role

Validate the rendered interface, not only source code. Prefer Playwright/browser tooling available in the current harness.

## 1. Determine validation scope

Before running screenshots:

- identify changed routes/components;
- identify the primary user flow;
- inspect project breakpoints/theme conventions;
- identify relevant loading/empty/error/disabled states;
- identify motion that requires reduced-motion verification.

## 2. Viewports

Do not hardcode the same four sizes for every project.

Test a representative set that includes:

- one mobile width;
- one laptop/desktop width;
- widths immediately below/inside/above important project breakpoints when layout changes there.

Usually 3–5 viewports are enough. Add more only when evidence indicates a breakpoint-specific problem.

## 3. Checks

### Render

- clipping/overlap;
- horizontal overflow;
- unreadable or truncated essential text;
- broken grids/tables;
- inconsistent spacing/alignment;
- images/aspect ratios;
- sticky/fixed element collisions.

### Interaction

- primary CTA/action works;
- menu/dialog/dropdown/focus trap when relevant;
- disabled/loading/error/empty states when relevant;
- visible hover/focus/active states;
- keyboard traversal for critical controls.

### Runtime

- relevant console errors;
- failed network requests caused by the change;
- hydration/runtime warnings when applicable.

### Motion

- reduced-motion path works when motion exists;
- no layout-shifting animation;
- no obvious scroll/jank regression in the changed interaction.

## 4. Evidence

Capture screenshots for representative states and viewports. Store/report paths in the migration or task report. A baseline-before image is useful when available, but absence of a historical baseline must not block validation of correctness.

## 5. Bounded correction

If problems are found:

1. batch the findings;
2. fix them together;
3. run one confirmation pass;
4. allow at most one additional correction pass.

Maximum automatic correction passes: **2**.

If still failing, stop and report the remaining issue instead of polishing indefinitely.

## Completion report

Include:

- routes/states tested;
- viewports used;
- findings fixed;
- screenshots/evidence;
- unresolved failures if any.
