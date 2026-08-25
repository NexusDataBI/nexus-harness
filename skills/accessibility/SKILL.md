---
name: accessibility
description: "Canonical Nexus accessibility skill. Merged unique guidance from better-accessibility and fixing-accessibility. Use when building, auditing, or fixing keyboard, name, focus, form, motion, or WCAG issues."
---

# accessibility

Canonical a11y skill. Contrast measurement and color fixes belong to `better-colors`. Text sizing and iOS input zoom belong to `better-typography`. Spatial RTL belongs to `better-layout`. Motion _design_ belongs to `design-motion-principles`; this skill owns reduced-motion and announcement rules.

Prefer native platform behavior. Remove ARIA rather than add it when a native element already solves the problem. Write fixes in the project's styling system. Prefer minimal, targeted patches — do not rewrite unrelated UI or migrate libraries unless asked.

## Priority

| Priority | Category            | Impact      |
| -------- | ------------------- | ----------- |
| 1        | Accessible names    | critical    |
| 2        | Keyboard access     | critical    |
| 3        | Focus and dialogs   | critical    |
| 4        | Semantics           | high        |
| 5        | Forms and errors    | high        |
| 6        | Announcements       | medium-high |
| 7        | Contrast and states | medium      |
| 8        | Media and motion    | low-medium  |
| 9        | Tool boundaries     | critical    |

## Native elements first

`<button>` for actions, `<a href>` for navigation. A real link must support Cmd/Ctrl/middle-click. Never `<div onClick>`. If a role is used, required ARIA attributes must be present. Lists use `ul`/`ol`/`li`. Do not skip heading levels. Tables use `th` for headers.

## Accessible names

Every interactive control has an accessible name. Icon-only buttons: `aria-label` (or labelledby); decorative SVG: `aria-hidden="true"`. Visible label text must appear in the accessible name. Links need meaningful text (no "click here"). Never put `aria-hidden="true"` on a focusable element.

## Keyboard

Every pointer path has a keyboard path. Tab between widgets; arrows inside composite widgets; Enter/Space activate; Escape closes overlays. Only `tabindex="0"` to join tab order and `tabindex="-1"` for programmatic focus. Positive tabindex is forbidden. Composite widgets use roving tabindex.

## Focus and dialogs

Style `:focus-visible`, not bare `:focus`. Never `outline: none` without a verified replacement. Custom rings need a project token and must survive adjacent colors and forced-colors. Modals: `inert` (or equivalent trap) on background, initial focus inside, restore focus to the trigger on close, `overscroll-behavior: contain`. Opening a dialog must not scroll the page unexpectedly.

## Hit areas

WCAG 2.5.8 AA baseline is 24×24 CSS pixels (with documented exceptions). Aim 44×44 touch / 40×40 desktop where density permits. Extended hit areas must not overlap; decorative layers get `pointer-events: none`.

## Forms and errors

Every input has a `<label for>` or wrapping `<label>`. Placeholder is never a label. Add `autocomplete`, meaningful `name`, correct `type`/`inputmode`. Never block paste. Keep submit enabled until the request starts, then disable with spinner + original label. Validate on submit. Failing fields: `aria-invalid="true"`, `aria-describedby` to the error, focus the first invalid field. Native `disabled` when truly unavailable; `aria-disabled="true"` only when it must stay focusable — then block pointer/keyboard/form in code. Required fields must be announced. Helper text is associated with the input. Disabled submit must explain why.

## Don't rely on color alone

Status needs a redundant cue. Hover-only interactions need a keyboard equivalent. Gate hover styling with `@media (hover: hover)` so tap does not stick.

## Motion, media, zoom

Wrap non-essential motion in `@media (prefers-reduced-motion: no-preference)`. Under reduced motion, replace slides/scales with opacity; kill parallax and autoplay. Autoplaying media needs a visible pause; action/error toasts stay until dismissed. Decorative images `alt=""`; informative images describe meaning; functional images describe the action. Captions when video has speech. Page works at 200% zoom and 320px width without horizontal scrolling. `min-height` not fixed `height` on text containers. Never cap user zoom in the viewport meta.

## Announcements

- `aria-describedby` — field-specific validation
- `role="status"` (polite) — non-urgent updates (toasts, counts)
- `role="alert"` — urgent untied errors only

Repeated polite announcements need a stable empty live region rendered before text updates. Loading: `aria-busy` or status text. Toasts must not be the only channel for critical information. Expandable controls: `aria-expanded` + `aria-controls`.

## Structure

One visible primary `<main>`. One `<h1>`, coherent outline. Skip-to-content is the first focusable control when chrome precedes main. Anchored headings get `scroll-margin-top`.

## Review and report

Two walks: keyboard-only (every flow completes) then screen reader (name, role, state). Quote the exact snippet, say why it matters, propose a small fix.

Severity: `HIGH` blocks a task, hides content from AT, or is systemic; `MEDIUM` makes interaction meaningfully harder; `LOW` is isolated polish. Verification without a browser: names, keyboard handlers, focus styles, reduced-motion guards, bound labels. With a browser: tab order, accessibility tree, visible focus, automated audit. Report unrun checks as `Not verified`.

| Severity | Location | Before | After | Why |
| -------- | -------- | ------ | ----- | --- |

`Block` if any `HIGH` remains, else `Approve`. Never approve coverage you did not inspect. Empty result: "No actionable accessibility findings" plus what was verified.

## Pending extract

Supporting reference files from `better-accessibility` (`semantics-and-aria.md`, `focus-and-keyboard.md`, `forms.md`, `hit-areas.md`, `motion-and-zoom.md`, `screen-readers.md`) remain in the v3 export until copied as optional skill references.
