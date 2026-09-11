# Nexus Frontend v2 + Behavioral Evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen `nexus-frontend` design direction/routing and add deterministic Harness behavioral-eval guidance/regression coverage.

**Architecture:** Keep `nexus-frontend` as the single frontend entrypoint and add Surface Intent, Design Read, design dials, and phase-scoped specialist routing. Keep eval ownership in the existing deterministic eval runner and route eval requirements from `nexus-workflow` rather than introducing another canonical lifecycle skill.

**Tech Stack:** Markdown agent skills, Python `unittest`, deterministic JSON eval cases, Nexus Harness lockfile hashing.

**Spec:** `docs/superpowers/specs/2026-09-11-nexus-frontend-v2-evals-design.md`

## Global Constraints

- No second frontend entrypoint or lifecycle spine.
- No live/paid model dependency for deterministic release PASS.
- No remote mutation from evals.
- No large unpinned external catalog vendoring in this change.
- Generated `dist/` content is not edited by hand.

---

### Task 1: Frontend v2 contract tests

**Files:**
- Modify: `tests/test_frontend_skill.py`

**Interfaces:**
- Consumes: existing `nexus-frontend` file/reference layout.
- Produces: contract assertions for Surface Intent, Design Read, dials, anti-default rules, and advisory intelligence routing.

- [ ] **Step 1: Add failing contract assertions** for `persuade|operate|read|experience`, `design-read.md`, `surface-intent.md`, `design-direction.md`, dials, `frontend-design`, and advisory-only `ui-ux-pro-max`.
- [ ] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_frontend_skill -v`

Expected: FAIL because new references/contracts do not exist in the baseline.

- [ ] **Step 3: Do not change production skill yet.**

---

### Task 2: Implement frontend v2 routing

**Files:**
- Modify: `skills/nexus-frontend/SKILL.md`
- Modify: `skills/nexus-frontend/references/router.md`
- Create: `skills/nexus-frontend/references/design-read.md`
- Create: `skills/nexus-frontend/references/surface-intent.md`
- Create: `skills/nexus-frontend/references/design-direction.md`

**Interfaces:**
- Consumes: authority order and retained specialists from v4.
- Produces: Surface Contract, Design Read contract, phase budgets, optional direction/intelligence routing.

- [ ] **Step 1: Add the two-axis Surface Contract.**
- [ ] **Step 2: Add Design Read and 1–10 design dials.**
- [ ] **Step 3: Route specialists by phase, with exactly one direction owner per pass.**
- [ ] **Step 4: Treat `ui-ux-pro-max` as advisory only and optional; treat `frontend-design` as optional direction ownership.**
- [ ] **Step 5: Add anti-default/uniqueness rule and preserve-vs-redesign behavior.**
- [ ] **Step 6: Run GREEN**

Run: `python3 -m unittest tests.test_frontend_skill -v`

Expected: PASS.

---

### Task 3: Behavioral eval gate tests

**Files:**
- Create: `tests/test_workflow_eval_guidance.py`

**Interfaces:**
- Consumes: `nexus-workflow`.
- Produces: a contract that distinguishes Harness behavior evals from ordinary product tests.

- [ ] **Step 1: Write failing tests** requiring the Behavioral Eval Gate and `references/evals.md`.
- [ ] **Step 2: Run RED**

Run: `python3 -m unittest tests.test_workflow_eval_guidance -v`

Expected: FAIL because the reference/gate is absent.

---

### Task 4: Implement behavioral eval guidance

**Files:**
- Modify: `skills/nexus-workflow/SKILL.md`
- Create: `skills/nexus-workflow/references/evals.md`

**Interfaces:**
- Consumes: existing Stage 3/Stage 6 lifecycle and deterministic eval runner.
- Produces: explicit trigger, baseline/RED, GREEN/regression, and invariant rules.

- [ ] **Step 1: Add Stage 3 Behavioral Eval Gate.**
- [ ] **Step 2: Add Stage 6 candidate + regression rerun requirement.**
- [ ] **Step 3: Document required/not-required cases and deterministic invariants.**
- [ ] **Step 4: Run GREEN**

Run: `python3 -m unittest tests.test_workflow_eval_guidance -v`

Expected: PASS.

---

### Task 5: Add frontend governance regression eval

**Files:**
- Create: `evals/cases/frontend-redesign-governance.json`

**Interfaces:**
- Consumes: existing `src/nexus_harness/evals.py`, `profiles/projects/sdr-platform.toml`, strict quality profile.
- Produces: architectural frontend regression coverage for tracking shape, affected checks, visual gating, completion, and no remote/model mutation.

- [ ] **Step 1: Add the architectural frontend eval case.**
- [ ] **Step 2: Run the deterministic eval suite.**

Run: `PYTHONPATH=src python3 -m unittest tests.test_evals -v`

Expected: PASS, including the new case loaded automatically by `run_evals`.

---

### Task 6: Regenerate lock and verify

**Files:**
- Modify: `harness.lock`
- Create: `docs/superpowers/specs/2026-09-11-nexus-frontend-v2-evals-design.md`
- Create: `docs/superpowers/plans/2026-09-11-nexus-frontend-v2-evals.md`

**Interfaces:**
- Consumes: final canonical skill/reference contents.
- Produces: fresh canonical hashes and reviewable design/plan artifacts.

- [ ] **Step 1: Regenerate the lock; do not hand-edit generated `dist/`.**

Run:

```bash
PYTHONPATH=src python3 -c "from pathlib import Path; from nexus_harness.lockfile import write_lock; write_lock(Path('.'))"
```

Expected: `harness.lock` records the final canonical skill/reference hashes; generated/engine hashes remain derived from repository sources.
- [ ] **Step 2: Run focused tests.**

Run:
`python3 -m unittest tests.test_frontend_skill tests.test_workflow_eval_guidance tests.test_evals -v`

Expected: PASS.

- [ ] **Step 3: Run repository validation/full suite using the project's documented command.**
- [ ] **Step 4: Confirm `git diff --check` is clean.**
- [ ] **Step 5: Fresh-review the diff against the spec and acceptance criteria.**
