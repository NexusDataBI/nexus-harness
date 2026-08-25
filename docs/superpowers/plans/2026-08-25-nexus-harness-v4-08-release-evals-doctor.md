# Nexus Harness v4 — Release, Evals & Doctor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the complete harness against deterministic acceptance criteria, produce migration evidence, package a reproducible release and cut over with rollback.

**Architecture:** The final phase adds one CLI, doctor diagnostics, deterministic policy evals, migration reporting, reproducible release assembly and an evidence-backed acceptance matrix before any user configuration is replaced.

**Tech Stack:** Python 3.11+ standard library, Git, shell, generated runtime configs

**Spec:** `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`

## Global Constraints

- Python runtime floor is 3.11 so TOML is parsed with the standard-library `tomllib` module.
- Canonical machine configuration uses TOML/JSON; no YAML parser is introduced into the harness runtime.
- The original `nexus-harness-export-20260825-094238.tar.gz` is immutable; all destructive cleanup occurs only in a v4 working copy.
- No project-specific IP, SSH target, absolute project path, client secret or model name belongs in `core/constitution.md`.
- Generated `dist/` content is never edited by hand; drift is a validation failure.
- Tests use Python standard-library `unittest` unless a target project already has its own test runner.
- Every implementation task is performed test-first where behavior can be isolated.
- Release claims require executed evidence; narrative assertions are insufficient.
- Model-dependent evals are optional and must not be required to prove deterministic policy correctness.
- Cutover is staged and reversible; v3 remains backed up until real v4 smoke usage succeeds.

---

## File Structure

- `src/nexus_harness/cli.py` — stable user/agent command surface
- `src/nexus_harness/doctor.py` — diagnostics
- `src/nexus_harness/evals.py` — deterministic eval runner
- `src/nexus_harness/migration_report.py` — before/after audit
- `src/nexus_harness/release.py` — release assembly
- `docs/release/v4-acceptance.md` — evidence matrix
- `docs/operations/cutover.md` — staged installation

---

### Task 1: Implement top-level Nexus CLI and command contracts

**Files:**
- Create: `src/nexus_harness/cli.py`
- Create: `scripts/nexus`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: All previously implemented modules.
- Produces: Stable command surface for validate/build/install/doctor/workflow/quality/project/frontend/incidents.

- [ ] **Step 1: Write failing CLI help test**

Create `tests/test_cli.py`:

```python
import subprocess
import unittest

class CliTests(unittest.TestCase):
    def test_help_lists_core_commands(self):
        result = subprocess.run(
            ["bash", "scripts/nexus", "--help"],
            text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0)
        for name in ("validate", "build", "install", "doctor", "workflow",
                     "quality", "project", "frontend", "incidents"):
            self.assertIn(name, result.stdout)
```

- [ ] **Step 2: Run CLI test and confirm RED**

Run: `python3 -m unittest tests.test_cli -v`

Expected: missing CLI.

- [ ] **Step 3: Implement argparse command tree**

Use Python `argparse` only. Each command delegates to an existing module; do not duplicate business rules in CLI parsing. `--json` returns structured machine output for agents/hooks, while default output is concise human-readable text.

Implementation contract:

```text
Implement argparse command tree
Use Python `argparse` only. Each command delegates to an existing module; do not duplicate business rules in CLI parsing. `--json` returns structured machine output for agents/hooks, while default output is concise human-readable text.
```


- [ ] **Step 4: Create stable shell launcher**

Create executable `scripts/nexus`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m nexus_harness.cli "$@"
```

- [ ] **Step 5: Run CLI tests**

Run: `python3 -m unittest tests.test_cli -v`

Expected: PASS.

- [ ] **Step 6: Commit CLI surface**

Run: `git add src/nexus_harness/cli.py scripts/nexus tests/test_cli.py && git commit -m "feat: expose nexus harness cli"`.

---

### Task 2: Implement doctor for local runtime, adapters and managed projects

**Files:**
- Create: `src/nexus_harness/doctor.py`
- Create: `tests/test_doctor.py`
- Create: `docs/operations/doctor.md`

**Interfaces:**
- Consumes: Canonical config, generated lock, runtime install state, tool availability and project registry.
- Produces: One diagnostic report that tells exactly what is ready, degraded or blocked.

- [ ] **Step 1: Write failing doctor status test**

Create `tests/test_doctor.py`:

```python
import unittest
from nexus_harness.doctor import DoctorCheck, summarize

class DoctorTests(unittest.TestCase):
    def test_required_failure_makes_doctor_fail(self):
        result = summarize([
            DoctorCheck("python", "PASS", required=True),
            DoctorCheck("generated-drift", "FAIL", required=True),
        ])
        self.assertEqual(result.gate, "FAIL")
```

- [ ] **Step 2: Run doctor test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_doctor -v`

Expected: import failure.

- [ ] **Step 3: Implement doctor checks**

Check Python floor, Git, `gh`, generated drift, canonical validation, runtime adapter install targets, task-state directory permissions, project registry, PostHog config presence when enabled, CI host profile, and availability of Biome/Vitest/Playwright/Trivy only when the selected project requires them.

Implementation contract:

```text
Implement doctor checks
Check Python floor, Git, `gh`, generated drift, canonical validation, runtime adapter install targets, task-state directory permissions, project registry, PostHog config presence when enabled, CI host profile, and availability of Biome/Vitest/Playwright/Trivy only when the selected project requires them.
```


- [ ] **Step 4: Render actionable doctor output**

Each failure prints the exact command or configuration file needed to repair it. Optional integrations report `SKIP` rather than false failure.

Implementation contract:

```text
Render actionable doctor output
Each failure prints the exact command or configuration file needed to repair it. Optional integrations report `SKIP` rather than false failure.
```


- [ ] **Step 5: Run doctor tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_doctor -v`

Expected: PASS.

- [ ] **Step 6: Commit doctor**

Run: `git add src/nexus_harness/doctor.py tests/test_doctor.py docs/operations/doctor.md && git commit -m "feat: add nexus doctor"`.

---

### Task 3: Create private eval fixtures for representative engineering tasks

**Files:**
- Create: `evals/cases/*.json`
- Create: `src/nexus_harness/evals.py`
- Create: `tests/test_evals.py`

**Interfaces:**
- Consumes: Workflow, graph, quality, security, frontend and project-governance behavior.
- Produces: Deterministic fixture suite that catches regressions in routing/gates without requiring live model calls.

- [ ] **Step 1: Write failing eval-loader test**

Create `tests/test_evals.py`:

```python
import unittest
from pathlib import Path
from nexus_harness.evals import load_cases

class EvalTests(unittest.TestCase):
    def test_required_eval_cases_exist(self):
        names = {case.name for case in load_cases(Path("evals/cases"))}
        required = {
            "backend-bug", "frontend-feature", "multi-file-refactor",
            "database-migration", "auth-security", "long-horizon",
            "ambiguous-task", "production-deploy-dry-run"
        }
        self.assertTrue(required.issubset(names))
```

- [ ] **Step 2: Run eval-loader test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_evals -v`

Expected: import failure/missing cases.

- [ ] **Step 3: Create eight deterministic eval cases**

Each JSON case defines input classification, expected tracking requirement, required graph/check nodes, approval requirements, expected completion/ship behavior and prohibited behavior. The production deploy case must require explicit approval and immutable digest.

Implementation contract:

```text
Create eight deterministic eval cases
Each JSON case defines input classification, expected tracking requirement, required graph/check nodes, approval requirements, expected completion/ship behavior and prohibited behavior. The production deploy case must require explicit approval and immutable digest.
```


- [ ] **Step 4: Implement eval runner**

Load cases, run deterministic classifiers/policies and emit pass/fail per expectation. Keep model-quality evals as a separate optional layer so release correctness does not depend on paid inference.

Implementation contract:

```text
Implement eval runner
Load cases, run deterministic classifiers/policies and emit pass/fail per expectation. Keep model-quality evals as a separate optional layer so release correctness does not depend on paid inference.
```


- [ ] **Step 5: Run deterministic eval suite**

Run: `PYTHONPATH=src python3 -m nexus_harness.evals evals/cases`.

Expected: all eight cases PASS.

- [ ] **Step 6: Commit eval suite**

Run: `git add evals src/nexus_harness/evals.py tests/test_evals.py && git commit -m "test: add nexus harness policy evals"`.

---

### Task 4: Create migration compatibility checks against the exported v3 package

**Files:**
- Create: `src/nexus_harness/migration_report.py`
- Create: `tests/test_migration_report.py`
- Create: `docs/migration/final-report.md`

**Interfaces:**
- Consumes: v3 baseline, cleanup report, skill ledger and final v4 inventory.
- Produces: Before/after evidence for files, duplicates, bytes, retained unique heuristics and removed dirty configuration.

- [ ] **Step 1: Write failing migration-report test**

Create `tests/test_migration_report.py` asserting the final report model includes:
- source archive SHA;
- before/after file count;
- before/after duplicate count/bytes;
- list of canonical skills;
- list of removed global project-specific config classes;
- unresolved divergent-skill decisions count equal to zero.

Implementation contract:

```text
Write failing migration-report test
Create `tests/test_migration_report.py` asserting the final report model includes: - source archive SHA; - before/after file count; - before/after duplicate count/bytes; - list of canonical skills; - list of removed global project-specific config classes; - unresolved divergent-skill decisions count equal to zero.
```


- [ ] **Step 2: Run migration-report test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_migration_report -v`

Expected: missing report implementation.

- [ ] **Step 3: Implement migration report generator**

Compare frozen v3 baseline with current canonical tree plus generated dist. Distinguish intentional generated repetition from manually maintained duplicates. Report every semantic merge decision from `skill-ledger.json`.

Implementation contract:

```text
Implement migration report generator
Compare frozen v3 baseline with current canonical tree plus generated dist. Distinguish intentional generated repetition from manually maintained duplicates. Report every semantic merge decision from `skill-ledger.json`.
```


- [ ] **Step 4: Generate final migration report**

Run the generator against the immutable source archive baseline and v4 working tree. Include explicit confirmation that original archive SHA is unchanged.

Implementation contract:

```text
Generate final migration report
Run the generator against the immutable source archive baseline and v4 working tree. Include explicit confirmation that original archive SHA is unchanged.
```


- [ ] **Step 5: Run migration report tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_migration_report -v`

Expected: PASS.

- [ ] **Step 6: Commit migration evidence**

Run: `git add src/nexus_harness/migration_report.py tests/test_migration_report.py docs/migration/final-report.md && git commit -m "docs: finalize harness migration report"`.

---

### Task 5: Implement reproducible release build and archive

**Files:**
- Create: `src/nexus_harness/release.py`
- Create: `tests/test_release.py`
- Create: `scripts/build`

**Interfaces:**
- Consumes: Validated canonical tree, generated adapters, lockfile, eval results.
- Produces: Reproducible release directory/archive plus manifest with hashes.

- [ ] **Step 1: Write failing reproducible-manifest test**

Create `tests/test_release.py` that builds the release manifest twice with the same inputs and asserts identical sorted file hashes and schema/version metadata. The test ignores archive mtime bytes and compares the logical manifest instead.

Implementation contract:

```text
Write failing reproducible-manifest test
Create `tests/test_release.py` that builds the release manifest twice with the same inputs and asserts identical sorted file hashes and schema/version metadata. The test ignores archive mtime bytes and compares the logical manifest instead.
```


- [ ] **Step 2: Run release test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_release -v`

Expected: missing release builder.

- [ ] **Step 3: Implement release preconditions**

Release refuses to run unless `scripts/validate`, full unittest suite, deterministic evals, runtime golden tests and generated drift checks pass. It also rejects upstream revisions that are missing or not valid hashes and rejects unresolved migration decisions.

Implementation contract:

```text
Implement release preconditions
Release refuses to run unless `scripts/validate`, full unittest suite, deterministic evals, runtime golden tests and generated drift checks pass. It also rejects upstream revisions that are missing or not valid hashes and rejects unresolved migration decisions.
```


- [ ] **Step 4: Implement release assembly**

Create `release/nexus-harness-v4/` containing canonical source, generated dist, scripts, docs, migration report, lockfile and install instructions. Exclude task state, secrets, caches, v3 source archive and Git metadata.

Implementation contract:

```text
Implement release assembly
Create `release/nexus-harness-v4/` containing canonical source, generated dist, scripts, docs, migration report, lockfile and install instructions. Exclude task state, secrets, caches, v3 source archive and Git metadata.
```


- [ ] **Step 5: Generate manifest and compressed archive**

Write `release/MANIFEST.json` with SHA-256 per file and create `nexus-harness-v4.tar.gz` using stable sorted paths. Archive reproducibility is validated by extracted file hashes rather than gzip timestamp bytes unless the implementation also normalizes gzip metadata.

Implementation contract:

```text
Generate manifest and compressed archive
Write `release/MANIFEST.json` with SHA-256 per file and create `nexus-harness-v4.tar.gz` using stable sorted paths. Archive reproducibility is validated by extracted file hashes rather than gzip timestamp bytes unless the implementation also normalizes gzip metadata.
```


- [ ] **Step 6: Run release tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_release -v`

Expected: PASS.

- [ ] **Step 7: Commit release builder**

Run: `git add src/nexus_harness/release.py scripts/build tests/test_release.py && git commit -m "feat: build reproducible harness release"`.

---

### Task 6: Perform full acceptance, security and smoke verification

**Files:**
- Create: `docs/release/v4-acceptance.md`
- Create: `tests/test_acceptance_matrix.py`

**Interfaces:**
- Consumes: All eight implementation plans.
- Produces: Machine-checked mapping from every final-spec success criterion to evidence.

- [ ] **Step 1: Create success-criteria matrix**

Represent all 20 final-spec success criteria in `tests/test_acceptance_matrix.py` with an evidence source: unit test, golden test, eval case, migration report field, generated-config assertion or doctor check. The matrix test fails if any criterion lacks evidence.

Implementation contract:

```text
Create success-criteria matrix
Represent all 20 final-spec success criteria in `tests/test_acceptance_matrix.py` with an evidence source: unit test, golden test, eval case, migration report field, generated-config assertion or doctor check. The matrix test fails if any criterion lacks evidence.
```


- [ ] **Step 2: Run full local verification**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v`.

Expected: all tests PASS.

- [ ] **Step 3: Run canonical validator and deterministic evals**

Run: `scripts/validate && scripts/nexus evals run`.

Expected: exit 0 and all required evals PASS.

- [ ] **Step 4: Compile and diff all runtime adapters**

Run: `scripts/nexus build adapters && scripts/diff`.

Expected: deterministic generated output and no unexplained installed drift.

- [ ] **Step 5: Run doctor in local and CI-host profiles**

Run: `scripts/nexus doctor --profile local` and, on the Nexus VPS, `nexus doctor --profile ci-host`.

Expected: required checks PASS; optional integrations may SKIP with reason.

- [ ] **Step 6: Run smoke installation with rollback**

Install v4 into a disposable test home, run Claude/Cursor/Codex config parse checks, then invoke rollback and confirm the previous generated tree is restored byte-for-byte.

- [ ] **Step 7: Write acceptance document**

Populate `docs/release/v4-acceptance.md` from actual command outputs/hashes. Do not mark a criterion PASS from narrative assertion alone.

Implementation contract:

```text
Write acceptance document
Populate `docs/release/v4-acceptance.md` from actual command outputs/hashes. Do not mark a criterion PASS from narrative assertion alone.
```


- [ ] **Step 8: Commit acceptance evidence**

Run: `git add docs/release/v4-acceptance.md tests/test_acceptance_matrix.py && git commit -m "test: verify nexus harness v4 acceptance"`.

---

### Task 7: Prepare controlled cutover from v3 to v4

**Files:**
- Create: `docs/operations/cutover.md`
- Create: `docs/operations/rollback.md`

**Interfaces:**
- Consumes: Passing v4 release, backup of current installed runtime config and user approval for installation.
- Produces: A reversible installation sequence with no silent overwrite.

- [ ] **Step 1: Document pre-cutover backup**

Record commands to archive current Claude/Cursor/Codex user configuration and current harness install into a timestamped local backup outside the v4 release directory.

- [ ] **Step 2: Document staged install order**

Install canonical Nexus core first, then generated adapters one runtime at a time: Codex test profile, Cursor test profile, Claude last because it has the richest hooks. Run `nexus doctor` after each runtime.

- [ ] **Step 3: Document rollback trigger**

Rollback immediately on runtime startup failure, repeated hook block without actionable reason, inability to parse generated settings, missing project access, or completion gate false positives in the smoke scenarios.

- [ ] **Step 4: Document v3 retirement rule**

Do not delete the v3 backup after cutover. Mark it read-only and retain it until at least one successful real task has completed through each of Claude, Cursor and Codex under v4.

- [ ] **Step 5: Run documentation link/path check**

Verify every referenced command/file exists in the release tree and no cutover instruction references the original user's absolute home path.

- [ ] **Step 6: Commit cutover runbook**

Run: `git add docs/operations/cutover.md docs/operations/rollback.md && git commit -m "docs: add nexus v4 cutover runbook"`.

---
