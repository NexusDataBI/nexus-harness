# Nexus Harness v4 — Frontend Visual QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make frontend quality browser- and vision-aware while consolidating overlapping frontend skills into one routed entrypoint.

**Architecture:** `nexus-frontend` chooses focused specialists, a dev-server manager provides a stable localhost, Playwright generates browser/trace/screenshot evidence, and visual findings participate in the same quality/completion gates as code checks.

**Tech Stack:** Python 3.11+, Playwright, retained Motion Principles/Impeccable references, browser-capable runtime reviewers

**Spec:** `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`

## Global Constraints

- Python runtime floor is 3.11 so TOML is parsed with the standard-library `tomllib` module.
- Canonical machine configuration uses TOML/JSON; no YAML parser is introduced into the harness runtime.
- The original `nexus-harness-export-20260825-094238.tar.gz` is immutable; all destructive cleanup occurs only in a v4 working copy.
- No project-specific IP, SSH target, absolute project path, client secret or model name belongs in `core/constitution.md`.
- Generated `dist/` content is never edited by hand; drift is a validation failure.
- Tests use Python standard-library `unittest` unless a target project already has its own test runner.
- Every implementation task is performed test-first where behavior can be isolated.
- Material visual frontend changes require current browser evidence.
- Motion is conditional and purposeful; skeleton/progress/lazy-loading are not applied mechanically to every element.
- Visual screenshots become stale when relevant UI code changes.
- Playwright is the only baseline E2E/visual automation tool.

---

## File Structure

- `skills/nexus-frontend/` — single frontend entry skill
- `core/quality/frontend.toml` — motion/loading/browser policy
- `src/nexus_harness/devserver.py` — localhost ownership/readiness
- `src/nexus_harness/playwright.py` — Playwright config/evidence execution
- `src/nexus_harness/visual.py` — visual evidence freshness
- `src/nexus_harness/frontend_review.py` — visual finding normalization

---

### Task 1: Consolidate frontend entrypoints into nexus-frontend modes

**Files:**
- Modify: `skills/nexus-frontend/SKILL.md`
- Create: `skills/nexus-frontend/references/router.md`
- Create: `tests/test_frontend_skill.py`

**Interfaces:**
- Consumes: Approved frontend skill consolidation map and retained upstream sources.
- Produces: One frontend entry skill with explicit modes and specialist routing.

- [ ] **Step 1: Write failing frontend-skill contract test**

Create `tests/test_frontend_skill.py`:

```python
import unittest
from pathlib import Path

class FrontendSkillTests(unittest.TestCase):
    def test_router_exposes_required_modes(self):
        text = Path("skills/nexus-frontend/SKILL.md").read_text(encoding="utf-8")
        for mode in ("implement", "redesign", "audit", "explain",
                     "visual-validate", "design-system", "polish"):
            self.assertIn(mode, text)
```

- [ ] **Step 2: Run frontend-skill test and confirm RED**

Run: `python3 -m unittest tests.test_frontend_skill -v`

Expected: missing modes or skill file.

- [ ] **Step 3: Merge unique routing guidance**

Move unique heuristics from `frontend-redesign-orchestrator`, `design-taste-frontend`, `baseline-ui`, `better-ui`, `better-interface`, `interface-review`, `explain-interface` and related broad entrypoints into the canonical router/reference files. Keep focused specialist sources such as Motion Principles and visual-validation separately routed.

- [ ] **Step 4: Document authority order**

In the canonical skill enforce: explicit task → project design system/brand → visual target/Figma → routed specialist → framework guidance. Prevent loading multiple generic visual specialists without a concrete reason.

- [ ] **Step 5: Run skill tests**

Run: `python3 -m unittest tests.test_frontend_skill -v`

Expected: PASS.

- [ ] **Step 6: Commit frontend consolidation**

Run: `git add skills/nexus-frontend tests/test_frontend_skill.py && git commit -m "feat: consolidate frontend workflow"`.

---

### Task 2: Codify Motion Principles and async-state policy

**Files:**
- Create: `core/quality/frontend.toml`
- Create: `skills/nexus-frontend/references/motion-policy.md`
- Create: `tests/test_motion_policy.py`

**Interfaces:**
- Consumes: Retained `design-motion-principles` upstream source.
- Produces: Reviewable motion/loading policy that avoids both missing feedback and decorative over-animation.

- [ ] **Step 1: Write failing motion-policy test**

Create `tests/test_motion_policy.py` that asserts the policy contains:
- `prefers-reduced-motion`;
- skeleton conditionality;
- lazy loading for non-critical resources;
- loading/empty/error state review;
- explicit prohibition on animating every element by default.

Implementation contract:

```text
Write failing motion-policy test
Create `tests/test_motion_policy.py` that asserts the policy contains: - `prefers-reduced-motion`; - skeleton conditionality; - lazy loading for non-critical resources; - loading/empty/error state review; - explicit prohibition on animating every element by default.
```


- [ ] **Step 2: Run motion-policy test and confirm RED**

Run: `python3 -m unittest tests.test_motion_policy -v`

Expected: missing policy files.

- [ ] **Step 3: Create frontend quality policy**

Require appropriate feedback for asynchronous interactions, but select skeleton/progress/optimistic UI based on actual waiting semantics. Require motion to clarify state, preserve accessibility, avoid layout shift and remain performant.

Implementation contract:

```text
Create frontend quality policy
Require appropriate feedback for asynchronous interactions, but select skeleton/progress/optimistic UI based on actual waiting semantics. Require motion to clarify state, preserve accessibility, avoid layout shift and remain performant.
```


- [ ] **Step 4: Link policy to Motion Principles**

The skill must route motion work to the retained upstream `design-motion-principles` source and record the upstream revision through `vendor-lock.json`; do not copy an unversioned duplicate into runtime roots.

- [ ] **Step 5: Run motion-policy tests**

Run: `python3 -m unittest tests.test_motion_policy -v`

Expected: PASS.

- [ ] **Step 6: Commit frontend motion policy**

Run: `git add core/quality/frontend.toml skills/nexus-frontend/references/motion-policy.md tests/test_motion_policy.py && git commit -m "feat: govern frontend motion and loading states"`.

---

### Task 3: Implement localhost dev-server manager

**Files:**
- Create: `src/nexus_harness/devserver.py`
- Create: `tests/test_devserver.py`

**Interfaces:**
- Consumes: Per-project `dev_server.command` and readiness URL from project profile.
- Produces: Start/reuse/stop ownership-aware local server lifecycle for browser QA.

- [ ] **Step 1: Write failing ownership test**

Create `tests/test_devserver.py`:

```python
import unittest
from nexus_harness.devserver import ServerState, should_stop

class DevServerTests(unittest.TestCase):
    def test_does_not_stop_preexisting_server(self):
        state = ServerState(pid=123, owned_by_harness=False, url="http://localhost:3000")
        self.assertFalse(should_stop(state))
```

- [ ] **Step 2: Run dev-server test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_devserver -v`

Expected: import failure.

- [ ] **Step 3: Implement readiness/reuse logic**

Probe the configured URL first. If healthy, record `owned_by_harness=false`. Otherwise spawn the configured command in its own process group, stream logs to task state and poll readiness until the profile timeout.

Implementation contract:

```text
Implement readiness/reuse logic
Probe the configured URL first. If healthy, record `owned_by_harness=false`. Otherwise spawn the configured command in its own process group, stream logs to task state and poll readiness until the profile timeout.
```


- [ ] **Step 4: Implement safe shutdown**

Only terminate process groups marked `owned_by_harness=true`. Preserve servers that existed before the verification session.

Implementation contract:

```text
Implement safe shutdown
Only terminate process groups marked `owned_by_harness=true`. Preserve servers that existed before the verification session.
```


- [ ] **Step 5: Run dev-server tests**

Add mocked readiness and timeout cases; run tests and expect PASS.

- [ ] **Step 6: Commit dev-server manager**

Run: `git add src/nexus_harness/devserver.py tests/test_devserver.py && git commit -m "feat: manage frontend localhost lifecycle"`.

---

### Task 4: Generate Playwright quality harness

**Files:**
- Create: `src/nexus_harness/playwright.py`
- Create: `templates/playwright/nexus.config.ts`
- Create: `tests/test_playwright_render.py`

**Interfaces:**
- Consumes: Project routes/viewports and dev-server readiness URL.
- Produces: Consistent E2E, screenshot, console/network and trace evidence.

- [ ] **Step 1: Write failing Playwright renderer test**

Create `tests/test_playwright_render.py` asserting generated config:
- uses the configured `baseURL`;
- defines desktop and mobile projects;
- retains trace/screenshots on failure;
- enables screenshot comparisons for visual assertions.

Implementation contract:

```text
Write failing Playwright renderer test
Create `tests/test_playwright_render.py` asserting generated config: - uses the configured `baseURL`; - defines desktop and mobile projects; - retains trace/screenshots on failure; - enables screenshot comparisons for visual assertions.
```


- [ ] **Step 2: Run renderer test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_playwright_render -v`

Expected: missing renderer/template.

Implementation contract:

```text
Run renderer test and confirm RED
Run: `PYTHONPATH=src python3 -m unittest tests.test_playwright_render -v` Expected: missing renderer/template.
```


- [ ] **Step 3: Create canonical Playwright config template**

Configure desktop Chromium and a representative mobile viewport by default. Preserve project override support. Retain `trace: on-first-retry`, failure screenshots and video only when the project profile opts in.

Implementation contract:

```text
Create canonical Playwright config template
Configure desktop Chromium and a representative mobile viewport by default. Preserve project override support. Retain `trace: on-first-retry`, failure screenshots and video only when the project profile opts in.
```


- [ ] **Step 4: Create evidence collection helper**

Expose `nexus frontend capture --route /path` that runs the matching Playwright scenario, stores screenshots/trace/test results under the current task state and registers each artifact with the evidence ledger.

Implementation contract:

```text
Create evidence collection helper
Expose `nexus frontend capture --route /path` that runs the matching Playwright scenario, stores screenshots/trace/test results under the current task state and registers each artifact with the evidence ledger.
```


- [ ] **Step 5: Run Playwright rendering tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_playwright_render -v`

Expected: PASS.

Implementation contract:

```text
Run Playwright rendering tests
Run: `PYTHONPATH=src python3 -m unittest tests.test_playwright_render -v` Expected: PASS.
```


- [ ] **Step 6: Commit Playwright harness**

Run: `git add src/nexus_harness/playwright.py templates/playwright tests/test_playwright_render.py && git commit -m "feat: standardize playwright visual evidence"`.

---

### Task 5: Implement visual evidence staleness and before/after bundles

**Files:**
- Create: `src/nexus_harness/visual.py`
- Create: `tests/test_visual.py`
- Create: `core/quality/visual-evidence.schema.json`

**Interfaces:**
- Consumes: Evidence ledger, changed-path set and screenshot artifacts.
- Produces: VisualEvidence bundles bound to diff hash and viewport/route.

- [ ] **Step 1: Write failing visual-staleness test**

Create `tests/test_visual.py`:

```python
import unittest
from nexus_harness.visual import VisualEvidence

class VisualTests(unittest.TestCase):
    def test_visual_evidence_is_stale_after_ui_diff_changes(self):
        ev = VisualEvidence(route="/", viewport="desktop", diff_hash="abc", screenshot="after.png")
        self.assertFalse(ev.is_fresh("def"))
```

- [ ] **Step 2: Run visual test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_visual -v`

Expected: import failure.

- [ ] **Step 3: Implement visual evidence object**

Store route, viewport, diff hash, baseline screenshot when applicable, final screenshot, trace, console error count, failed request count and reviewer status.

Implementation contract:

```text
Implement visual evidence object
Store route, viewport, diff hash, baseline screenshot when applicable, final screenshot, trace, console error count, failed request count and reviewer status.
```


- [ ] **Step 4: Implement material-change requirement**

For changes touching configured frontend visual paths, Stage 6 requires at least one current desktop and one current mobile screenshot unless the project profile explicitly classifies the change as non-visual.

Implementation contract:

```text
Implement material-change requirement
For changes touching configured frontend visual paths, Stage 6 requires at least one current desktop and one current mobile screenshot unless the project profile explicitly classifies the change as non-visual.
```


- [ ] **Step 5: Run visual tests**

Add required-viewports and non-visual skip cases; run tests and expect PASS.

- [ ] **Step 6: Commit visual evidence layer**

Run: `git add src/nexus_harness/visual.py tests/test_visual.py core/quality/visual-evidence.schema.json && git commit -m "feat: bind visual evidence to current diff"`.

---

### Task 6: Create frontend visual review report contract

**Files:**
- Create: `agents/frontend-visual-reviewer.md`
- Create: `src/nexus_harness/frontend_review.py`
- Create: `tests/test_frontend_review.py`

**Interfaces:**
- Consumes: Current screenshots, route metadata, console/network results, project design system and acceptance criteria.
- Produces: Structured visual findings and pass/fail input for Quality Gate.

- [ ] **Step 1: Write failing review-normalization test**

Create `tests/test_frontend_review.py` that normalizes a reviewer response containing:
- severity;
- confidence;
- screenshot/route reference;
- category (`layout`, `responsive`, `state`, `motion`, `accessibility`, `design-system`);
and confirms a `high` confirmed finding blocks the visual gate.

Implementation contract:

```text
Write failing review-normalization test
Create `tests/test_frontend_review.py` that normalizes a reviewer response containing: - severity; - confidence; - screenshot/route reference; - category (`layout`, `responsive`, `state`, `motion`, `accessibility`, `design-system`); and confirms a `high` confirmed finding blocks the visual gate.
```


- [ ] **Step 2: Run review test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_frontend_review -v`

Expected: missing normalizer.

- [ ] **Step 3: Write fresh-context reviewer instructions**

The agent receives screenshots, task acceptance criteria, design-system references and browser evidence, not the implementer's full conversation. It must compare behavior across required viewports and identify concrete visual/runtime defects with location/evidence.

Implementation contract:

```text
Write fresh-context reviewer instructions
The agent receives screenshots, task acceptance criteria, design-system references and browser evidence, not the implementer's full conversation. It must compare behavior across required viewports and identify concrete visual/runtime defects with location/evidence.
```


- [ ] **Step 4: Implement reviewer normalization**

Parse structured findings into the generic finding model used by Plan 2. Confirmed blocker/high visual findings fail Quality Gate; medium/low are retained in the report.

Implementation contract:

```text
Implement reviewer normalization
Parse structured findings into the generic finding model used by Plan 2. Confirmed blocker/high visual findings fail Quality Gate; medium/low are retained in the report.
```


- [ ] **Step 5: Run review tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_frontend_review -v`

Expected: PASS.

- [ ] **Step 6: Commit visual reviewer**

Run: `git add agents/frontend-visual-reviewer.md src/nexus_harness/frontend_review.py tests/test_frontend_review.py && git commit -m "feat: add evidence-based frontend review"`.

---

### Task 7: Add frontend integration scenario

**Files:**
- Create: `tests/test_frontend_integration.py`

**Interfaces:**
- Consumes: Frontend router, dev server manager, Playwright renderer, visual evidence and reviewer gate.
- Produces: Proof that a material UI task cannot complete without current browser evidence.

- [ ] **Step 1: Create the integration test**

Simulate a frontend task with current diff `abc`; record desktop/mobile visual evidence and PASS review; confirm completion can pass. Change diff to `def`; confirm the same task becomes blocked until new visual evidence is recorded.

Implementation contract:

```text
Create the integration test
Simulate a frontend task with current diff `abc`; record desktop/mobile visual evidence and PASS review; confirm completion can pass. Change diff to `def`; confirm the same task becomes blocked until new visual evidence is recorded.
```


- [ ] **Step 2: Run frontend integration test**

Run: `PYTHONPATH=src python3 -m unittest tests.test_frontend_integration -v`

Expected: PASS.

- [ ] **Step 3: Run Plan 6 full verification**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v && scripts/validate`.

Expected: PASS.

- [ ] **Step 4: Commit Plan 6 completion**

Run: `git add tests/test_frontend_integration.py && git commit -m "test: prove frontend visual quality gate"`.

---
