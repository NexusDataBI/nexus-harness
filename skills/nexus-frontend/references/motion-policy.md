# Motion and async-state policy

Nexus review contract for motion and loading feedback. Machine-readable flags live in `core/quality/frontend.toml`. This file does not copy Motion Principles.

## Source of truth

Motion decisions come from the locked source `upstream/design-motion-principles`, recorded in `upstream/vendor-lock.json`. Do not vendor a second unversioned copy into runtime roots (`skills/`).

## Ask first

Before adding animation, ask “should this animate at all?”.
Do not animate every element by default. Motion is not required on every change; use it only when it improves comprehension of state.

## Accessibility

Respect `prefers-reduced-motion`. Route a11y details to the `accessibility` skill.

## Skeletons

Skeletons are conditional: only when the wait is meaningful and the content shape is predictable. This is not skeleton-everywhere.

## Async states

Review loading, empty, error, disabled, and transition states for every asynchronous interaction that needs user feedback.

## Progress

Show progress only when measurable or significant. Do not invent a determinate bar for an unknown wait.

## Optimistic UI

Use optimistic UI only when rollback is safe. If the user cannot recover from a failed write, wait for the server.

## Lazy loading

Use lazy loading for non-critical resources (routes, components, media). Keep critical path assets eager.

## Avoid

- hover scale everywhere
- decorative stagger
- bounce/spring for routine productivity UI
- layout shift
- animation blocking interaction
