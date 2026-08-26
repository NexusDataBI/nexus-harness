# Task 1 Report — Frontend router consolidation

## Status

DONE

## Implemented

- Extended `tests/test_frontend_skill.py` (existing mode/legacy assertions kept).
- Added `skills/nexus-frontend/references/router.md` (authority order, load budget, retained specialists, no multi-generic load).
- Extended `skills/nexus-frontend/SKILL.md` to point at the router and collapse precedence to six levels.
- P1-D05 frontend slice only: evaluated `ui-styling`, `ui-ux-pro-max`, and `better-accessibility` refs.
- PRESERVE: six `better-accessibility` reference files under `skills/accessibility/references/` (hashes match the v3 export). Did not copy `agents/openai.yaml`.
- Refreshed `harness.lock` canonical hashes for the changed/added skill files (skills/ is in `canonical_hashes`; engine Python unchanged).

## P1-D05 slice — PRESERVE / COVERED / DISCARD

| Source                      | Decision        | Outcome                                                                                                                                                                                      |
| --------------------------- | --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ui-styling`                | ALREADY COVERED | Stack-honor / do-not-impose-shadcn is in `nexus-frontend` implement + router. Encyclopedia, CLI recipes, and scripts DISCARD (generic shadcn/Tailwind docs; remain in the immutable export). |
| `ui-ux-pro-max` (3 hashes)  | PRESERVE        | Search/explore contract and “recommendations never outrank brand/Figma/brief” in `references/router.md`. Catalogs, scripts, and the three divergent entrypoints DISCARD (export only).       |
| `better-accessibility` refs | PRESERVE        | Copied to `skills/accessibility/references/`. Same `accessibility` skill; no second a11y product.                                                                                            |

P1-D05 is **not** marked resolved. Remaining pending: implement Claude vs Codex, code-review, tdd-workflow, root-cause-tracing, napkin, Superpowers host-runtime.

`docs/migration/debt.json` status for P1-D05 left `deferred`.

## TDD evidence

### RED

Command:

```text
python3 -m unittest tests.test_frontend_skill -v
```

Observed (abridged):

```text
test_uses_canonical_routing_names ... ok
test_router_documents_authority_order ... FAIL
  AssertionError: missing skills/nexus-frontend/references/router.md
test_router_names_retained_specialists ... ERROR
  FileNotFoundError: .../skills/nexus-frontend/references/router.md
test_router_forbids_multi_generic_load ... ERROR
  FileNotFoundError: .../skills/nexus-frontend/references/router.md
test_accessibility_optional_references_exist ... FAIL
  missing skills/accessibility/references/semantics-and-aria.md
test_frontend_heuristic_slice_is_evaluated ... FAIL
  ui-styling row must record PRESERVE, ALREADY COVERED, or DISCARD
Ran 6 tests in 0.002s
FAILED (failures=3, errors=2)
```

Existing `test_uses_canonical_routing_names` stayed green. New tests failed for the expected missing files / pending rows.

### GREEN

Command:

```text
python3 -m unittest tests.test_frontend_skill -v
```

Observed:

```text
test_accessibility_optional_references_exist ... ok
test_frontend_heuristic_slice_is_evaluated ... ok
test_router_documents_authority_order ... ok
test_router_forbids_multi_generic_load ... ok
test_router_names_retained_specialists ... ok
test_uses_canonical_routing_names ... ok
Ran 6 tests in 0.002s
OK
```

Also: `PYTHONPATH=src python3 -m unittest tests.test_validate.ValidateTests.test_repository_has_no_appledouble_or_generated_drift tests.test_skill_contracts -v` and `scripts/validate` — PASS.

## Files changed

- `tests/test_frontend_skill.py`
- `skills/nexus-frontend/SKILL.md`
- `skills/nexus-frontend/references/router.md`
- `skills/accessibility/SKILL.md`
- `skills/accessibility/references/{semantics-and-aria,focus-and-keyboard,forms,hit-areas,motion-and-zoom,screen-readers}.md`
- `docs/migration/unique-heuristics.md`
- `harness.lock`

## Concerns

- `write_lock` was required even though no engine Python changed: `skills/` is part of `canonical_hashes`. Only skill hash lines moved.
- Inputs tarball was read-only (`tar` extract to `/tmp`). Not mutated.
- Task 2 not started.
