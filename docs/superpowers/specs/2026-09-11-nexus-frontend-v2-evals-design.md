# Nexus Frontend v2 + Behavioral Evals Design

**Status:** approved in conversation on 2026-09-11

## Goal

Make `nexus-frontend` a stronger design orchestrator while preserving the Harness rule that one canonical entrypoint routes focused specialists. Add a deterministic behavioral-eval contract to the workflow without introducing a competing lifecycle or duplicating product tests.

## Frontend architecture

`nexus-frontend` remains the only canonical frontend entrypoint. It gains two explicit axes:

- **Surface Intent:** `persuade | operate | read | experience`
- **Surface Type:** `marketing | product | data-dense | motion | figma | architecture | validation`

The intent describes user success on the current surface. The type selects the specialist family. Product category alone must not choose visual style.

### Design Read

New surfaces, redesigns, and material visual-direction changes require a Design Read before implementation. It records subject, audience/context, primary job, authority, visual POV, one memorable move, three design dials (`variance`, `motion`, `density`), preserve constraints, and avoid-list.

Narrow bugfixes/refinements preserve incumbent identity and do not invent a new direction.

### Specialist model

Specialists are phase-scoped:

1. discover/authority;
2. direction/intelligence;
3. implementation;
4. harden/audit;
5. visual validation;
6. optional polish.

One direction owner is selected for a pass. `frontend-design` may own distinctive direction when available; Impeccable may own shape/new-work or polish; `ui-ux-pro-max` is bounded consultative/search intelligence only. None outrank explicit user instructions, project brand/design system, Figma, incumbent product truth, or an approved Design Read.

External host specialists remain optional so the Harness does not gain an unpinned runtime dependency in this change.

### Anti-slop

The system must not replace one generated default with another. Every material visual decision should be defensible from subject, audience, and primary job. The direction uses one memorable move and deliberate restraint around it.

## Behavioral eval architecture

Behavioral evals remain owned by the existing deterministic Harness eval runner and are routed by `nexus-workflow`; no new canonical `nexus-evals` entrypoint is introduced.

An eval is required for Harness behavior changes such as routing, classification, tracking, approval, completion, shipping/tool permission, quality-profile selection, visual/security gating, memory/incident governance, or a reproduced Harness regression.

Ordinary product code remains TDD + product tests + `nexus-verify`.

Lifecycle:

```text
expected behavior → eval case → baseline/RED → implementation
→ affected eval GREEN → full deterministic eval suite → review
```

Release PASS must remain independent of live/paid model calls and remote mutation.

## Files

Modify:
- `skills/nexus-frontend/SKILL.md`
- `skills/nexus-frontend/references/router.md`
- `skills/nexus-workflow/SKILL.md`
- `tests/test_frontend_skill.py`
- `harness.lock`

Create:
- `skills/nexus-frontend/references/design-read.md`
- `skills/nexus-frontend/references/surface-intent.md`
- `skills/nexus-frontend/references/design-direction.md`
- `skills/nexus-workflow/references/evals.md`
- `tests/test_workflow_eval_guidance.py`
- `evals/cases/frontend-redesign-governance.json`

## Constraints

- Do not create a second frontend entrypoint.
- Do not create a second lifecycle spine.
- Do not require a live model for deterministic eval PASS.
- Do not allow evals to mutate GitHub or other remote systems.
- Do not vendor a large external design catalog in this change.
- Do not hand-edit generated `dist/` content.
- Update `harness.lock` only through canonical file hashes (generated outputs are unaffected because the constitution/runtime adapters are unchanged).
