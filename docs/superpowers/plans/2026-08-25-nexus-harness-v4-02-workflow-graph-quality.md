# Nexus Harness v4 — Workflow, Graph, Quality & Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 0→9 state machine, DAG execution primitives, evidence ledger, Quality Ratchet, Trivy normalization, failure memory and deterministic completion gate.

**Architecture:** The lifecycle is authoritative for governance while a task DAG controls parallel execution and invalidation. Quality and security are structured deterministic gates whose evidence is bound to the current diff hash.

**Tech Stack:** Python 3.11+ standard library, TOML/JSON, Biome/Vitest/Playwright/Trivy result formats

**Spec:** `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`

## Global Constraints

- Python runtime floor is 3.11 so TOML is parsed with the standard-library `tomllib` module.
- Canonical machine configuration uses TOML/JSON; no YAML parser is introduced into the harness runtime.
- The original `nexus-harness-export-20260825-094238.tar.gz` is immutable; all destructive cleanup occurs only in a v4 working copy.
- No project-specific IP, SSH target, absolute project path, client secret or model name belongs in `core/constitution.md`.
- Generated `dist/` content is never edited by hand; drift is a validation failure.
- Tests use Python standard-library `unittest` unless a target project already has its own test runner.
- Every implementation task is performed test-first where behavior can be isolated.
- Acceptance criteria always initialize as FAIL and cannot be manually promoted without evidence.
- Quality/security blocking decisions are deterministic; aggregate scores cannot override a failed required gate.
- Trivy is the only security scanner introduced by the baseline harness.

---

## File Structure

- `src/nexus_harness/state.py` — task state and persistence
- `src/nexus_harness/workflow.py` — lifecycle transition guards
- `src/nexus_harness/graph.py` — DAG readiness/conflicts/invalidation
- `src/nexus_harness/evidence.py` — fresh evidence ledger
- `src/nexus_harness/quality.py` — quality profiles and Ratchet
- `src/nexus_harness/security.py` — Trivy normalization
- `src/nexus_harness/failures.py` — retry/no-progress memory
- `src/nexus_harness/completion.py` — Done Gate

---

### Task 1: Implement task state and lifecycle transitions

**Files:**
- Create: `src/nexus_harness/state.py`
- Create: `src/nexus_harness/workflow.py`
- Create: `tests/test_workflow.py`
- Create: `core/workflow/task-state.schema.json`

**Interfaces:**
- Consumes: Canonical lifecycle and classification policy from Plan 1.
- Produces: `TaskState`, legal transition validation, persisted per-task state and explicit stage statuses.

- [ ] **Step 1: Write the failing lifecycle transition test**

Create `tests/test_workflow.py`:

```python
import tempfile
import unittest
from pathlib import Path
from nexus_harness.state import TaskState, StageStatus
from nexus_harness.workflow import advance_stage

class WorkflowTests(unittest.TestCase):
    def test_cannot_enter_implement_without_acceptance(self):
        state = TaskState.new("task-1", "repo-1")
        state.stage = 4
        state.acceptance = []
        with self.assertRaises(ValueError):
            advance_stage(state, 5)
```

- [ ] **Step 2: Run lifecycle test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_workflow -v`

Expected: import failure.

- [ ] **Step 3: Implement task dataclasses and persistence**

Create `src/nexus_harness/state.py` with enums/dataclasses:

```python
from dataclasses import dataclass, field
from enum import StrEnum

class StageStatus(StrEnum):
    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"

@dataclass
class AcceptanceCriterion:
    id: str
    statement: str
    status: str = "FAIL"
    verification: dict = field(default_factory=dict)
    evidence_id: str | None = None

@dataclass
class TaskState:
    task_id: str
    repo_id: str
    stage: int = 0
    acceptance: list[AcceptanceCriterion] = field(default_factory=list)
    stage_status: dict[str, str] = field(default_factory=dict)

    @classmethod
    def new(cls, task_id: str, repo_id: str) -> "TaskState":
        return cls(task_id=task_id, repo_id=repo_id)
```

Add JSON load/save functions using atomic temp-file rename.

- [ ] **Step 4: Implement legal lifecycle transitions**

Create `src/nexus_harness/workflow.py` with `advance_stage(state, target_stage)` and guards from the final spec. Stage 5 rejects missing/empty acceptance on mutable tasks. Stage 8 delegates completion checks to `completion.py` introduced later in this plan.

Implementation contract:

```text
Implement legal lifecycle transitions
Create `src/nexus_harness/workflow.py` with `advance_stage(state, target_stage)` and guards from the final spec. Stage 5 rejects missing/empty acceptance on mutable tasks. Stage 8 delegates completion checks to `completion.py` introduced later in this plan.
```


- [ ] **Step 5: Run lifecycle tests and confirm GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_workflow -v`

Expected: PASS.

- [ ] **Step 6: Commit lifecycle state**

Run: `git add src/nexus_harness/state.py src/nexus_harness/workflow.py core/workflow/task-state.schema.json tests/test_workflow.py && git commit -m "feat: add nexus task lifecycle state"`.

---

### Task 2: Implement task graph, dependency resolution and resource conflicts

**Files:**
- Create: `src/nexus_harness/graph.py`
- Create: `tests/test_graph.py`
- Create: `core/graph/graph.schema.json`

**Interfaces:**
- Consumes: Task state and canonical graph edge semantics.
- Produces: `TaskGraph`, topological readiness, conflict detection and invalidation.

- [ ] **Step 1: Write failing graph tests**

Create `tests/test_graph.py`:

```python
import unittest
from nexus_harness.graph import GraphNode, TaskGraph

class GraphTests(unittest.TestCase):
    def test_independent_nodes_are_ready_together(self):
        graph = TaskGraph([
            GraphNode("backend", reads=("shared/schema.ts",), writes=("apps/server/a.ts",)),
            GraphNode("frontend", reads=("shared/schema.ts",), writes=("apps/web/a.ts",)),
        ])
        self.assertEqual({n.id for n in graph.ready_nodes()}, {"backend", "frontend"})

    def test_writers_of_same_resource_conflict(self):
        graph = TaskGraph([
            GraphNode("a", writes=("shared/schema.ts",)),
            GraphNode("b", writes=("shared/schema.ts",)),
        ])
        self.assertEqual(graph.conflicts(), {("a", "b")})
```

- [ ] **Step 2: Run graph tests and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_graph -v`

Expected: import failure.

- [ ] **Step 3: Implement graph nodes and readiness**

Implement immutable `GraphNode` with `id`, `stage`, `kind`, `depends_on`, `reads`, `writes`, `affected_paths`, `execution_target`, `risk`, `estimated_cost`, `status`. Implement `TaskGraph.ready_nodes()` by requiring dependencies to be `PASS/SKIP`.

Implementation contract:

```text
Implement graph nodes and readiness
Implement immutable `GraphNode` with `id`, `stage`, `kind`, `depends_on`, `reads`, `writes`, `affected_paths`, `execution_target`, `risk`, `estimated_cost`, `status`. Implement `TaskGraph.ready_nodes()` by requiring dependencies to be `PASS/SKIP`.
```


- [ ] **Step 4: Implement conflict and invalidation rules**

Implement write/write conflict detection; define `invalidate(changed_paths)` so evidence-producing nodes whose `affected_paths` overlap changed paths return to `PENDING` and their evidence IDs are cleared.

Implementation contract:

```text
Implement conflict and invalidation rules
Implement write/write conflict detection; define `invalidate(changed_paths)` so evidence-producing nodes whose `affected_paths` overlap changed paths return to `PENDING` and their evidence IDs are cleared.
```


- [ ] **Step 5: Run graph tests and confirm GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_graph -v`

Expected: PASS.

- [ ] **Step 6: Commit task graph**

Run: `git add src/nexus_harness/graph.py tests/test_graph.py core/graph/graph.schema.json && git commit -m "feat: add task graph scheduler primitives"`.

---

### Task 3: Implement evidence ledger and freshness

**Files:**
- Create: `src/nexus_harness/evidence.py`
- Create: `tests/test_evidence.py`

**Interfaces:**
- Consumes: Task graph and Git diff hash supplied by runtime adapters.
- Produces: Append-only structured evidence with freshness checks.

- [ ] **Step 1: Write failing evidence freshness test**

Create `tests/test_evidence.py`:

```python
import unittest
from nexus_harness.evidence import Evidence

class EvidenceTests(unittest.TestCase):
    def test_evidence_is_stale_for_different_diff(self):
        item = Evidence("ev-1", "vitest", 0, "abc123", "tests pass")
        self.assertFalse(item.is_fresh("def456"))
```

- [ ] **Step 2: Run evidence test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_evidence -v`

Expected: import failure.

- [ ] **Step 3: Implement evidence objects and JSONL ledger**

Implement `Evidence(id, command, exit_code, diff_hash, summary, artifact=None, limitation=None, timestamp=...)`, `is_fresh(current_diff_hash)`, `append_evidence(path, evidence)` and `read_evidence(path)`.

Implementation contract:

```text
Implement evidence objects and JSONL ledger
Implement `Evidence(id, command, exit_code, diff_hash, summary, artifact=None, limitation=None, timestamp=...)`, `is_fresh(current_diff_hash)`, `append_evidence(path, evidence)` and `read_evidence(path)`.
```


- [ ] **Step 4: Run evidence tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_evidence -v`

Expected: PASS.

- [ ] **Step 5: Commit evidence ledger**

Run: `git add src/nexus_harness/evidence.py tests/test_evidence.py && git commit -m "feat: record verification evidence"`.

---

### Task 4: Implement quality profiles, report normalization and Ratchet

**Files:**
- Create: `src/nexus_harness/quality.py`
- Create: `tests/test_quality.py`
- Create: `core/quality/quality-report.schema.json`
- Create: `core/quality/ratchet.toml`

**Interfaces:**
- Consumes: Structured outputs from project-specific checks and `.nexus/quality/baseline.json`.
- Produces: `QualityReport`, absolute/ratchet/budget evaluation and baseline-governance rules.

- [ ] **Step 1: Write failing Ratchet tests**

Create `tests/test_quality.py`:

```python
import unittest
from nexus_harness.quality import Metric, evaluate_metric

class QualityTests(unittest.TestCase):
    def test_lower_is_better_ratchet_rejects_regression(self):
        metric = Metric("lint_warnings", current=13, baseline=12,
                        mode="ratchet", direction="lower")
        self.assertEqual(evaluate_metric(metric).status, "FAIL")

    def test_higher_is_better_ratchet_accepts_improvement(self):
        metric = Metric("coverage", current=81.0, baseline=80.0,
                        mode="ratchet", direction="higher")
        self.assertEqual(evaluate_metric(metric).status, "PASS")
```

- [ ] **Step 2: Run quality tests and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_quality -v`

Expected: import failure.

- [ ] **Step 3: Implement metric and report types**

Implement `Metric`, `MetricResult`, `QualityReport` and evaluators for `absolute`, `ratchet` and `budget`. A report gate fails when any required metric fails regardless of aggregate score.

Implementation contract:

```text
Implement metric and report types
Implement `Metric`, `MetricResult`, `QualityReport` and evaluators for `absolute`, `ratchet` and `budget`. A report gate fails when any required metric fails regardless of aggregate score.
```


- [ ] **Step 4: Implement baseline anti-weakening rules**

Implement `validate_baseline_change(base, proposed, measured)` so a proposed baseline cannot weaken any governed metric. If measured quality improves beyond the stored floor and the policy marks `promote_improvements = true`, the proposed baseline must equal the measured improvement within configured precision.

Implementation contract:

```text
Implement baseline anti-weakening rules
Implement `validate_baseline_change(base, proposed, measured)` so a proposed baseline cannot weaken any governed metric. If measured quality improves beyond the stored floor and the policy marks `promote_improvements = true`, the proposed baseline must equal the measured improvement within configured precision.
```


- [ ] **Step 5: Run Ratchet tests and add baseline-change cases**

Add tests for attempted coverage baseline reduction, lint-warning increase, and required promotion after an improvement. Run: `PYTHONPATH=src python3 -m unittest tests.test_quality -v`.

Expected: PASS.

- [ ] **Step 6: Commit Quality Gate core**

Run: `git add src/nexus_harness/quality.py tests/test_quality.py core/quality && git commit -m "feat: add quality ratchet"`.

---

### Task 5: Implement Trivy security report normalization

**Files:**
- Create: `src/nexus_harness/security.py`
- Create: `tests/fixtures/trivy.json`
- Create: `tests/test_security.py`
- Create: `core/security/security-report.schema.json`

**Interfaces:**
- Consumes: Trivy JSON output; no second security scanner.
- Produces: Normalized security findings and blocking policy.

- [ ] **Step 1: Write failing Trivy normalization test**

Create `tests/test_security.py`:

```python
import json
import unittest
from pathlib import Path
from nexus_harness.security import normalize_trivy

class SecurityTests(unittest.TestCase):
    def test_critical_vulnerability_blocks(self):
        payload = json.loads(Path("tests/fixtures/trivy.json").read_text())
        report = normalize_trivy(payload)
        self.assertEqual(report.gate, "FAIL")
        self.assertEqual(report.counts["critical"], 1)
```

- [ ] **Step 2: Create a minimal Trivy JSON fixture**

Create `tests/fixtures/trivy.json`:

```json
{
  "Results": [{
    "Target": "package-lock.json",
    "Vulnerabilities": [{
      "VulnerabilityID": "CVE-2099-0001",
      "PkgName": "example",
      "InstalledVersion": "1.0.0",
      "FixedVersion": "1.0.1",
      "Severity": "CRITICAL"
    }]
  }]
}
```

- [ ] **Step 3: Run security test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_security -v`

Expected: import failure.

- [ ] **Step 4: Implement Trivy normalizer and policy**

Normalize vulnerability, secret and misconfiguration results into one `SecurityReport`. Default policy blocks `CRITICAL` and blocks `HIGH` when a fixed version/remediation exists. Preserve raw IDs and target paths for the PR report.

Implementation contract:

```text
Implement Trivy normalizer and policy
Normalize vulnerability, secret and misconfiguration results into one `SecurityReport`. Default policy blocks `CRITICAL` and blocks `HIGH` when a fixed version/remediation exists. Preserve raw IDs and target paths for the PR report.
```


- [ ] **Step 5: Run security tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_security -v`

Expected: PASS.

- [ ] **Step 6: Commit security gate**

Run: `git add src/nexus_harness/security.py tests/test_security.py tests/fixtures/trivy.json core/security && git commit -m "feat: normalize trivy security gate"`.

---

### Task 6: Implement failure memory and no-progress detection

**Files:**
- Create: `src/nexus_harness/failures.py`
- Create: `tests/test_failures.py`

**Interfaces:**
- Consumes: Tool name, exit code and normalized stderr/stdout summary.
- Produces: Stable failure fingerprints and a `diagnose` signal after repeated unchanged failure.

- [ ] **Step 1: Write failing repeated-failure test**

Create `tests/test_failures.py`:

```python
import unittest
from nexus_harness.failures import FailureMemory

class FailureTests(unittest.TestCase):
    def test_second_identical_failure_requests_diagnosis(self):
        memory = FailureMemory()
        memory.record("vitest", 1, "AssertionError: expected 1 got 0")
        result = memory.record("vitest", 1, "AssertionError: expected 1 got 0")
        self.assertEqual(result.action, "diagnose")
```

- [ ] **Step 2: Run failure test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_failures -v`

Expected: import failure.

- [ ] **Step 3: Implement normalized fingerprints**

Strip timestamps, temp paths and volatile numeric IDs before hashing `(tool, exit_code, normalized_error)`. Track attempt count and whether the latest material input/diff hash changed.

Implementation contract:

```text
Implement normalized fingerprints
Strip timestamps, temp paths and volatile numeric IDs before hashing `(tool, exit_code, normalized_error)`. Track attempt count and whether the latest material input/diff hash changed.
```


- [ ] **Step 4: Implement no-progress decision**

Return `retry` on first failure, `diagnose` on second unchanged failure, and `blocked` after the configured ceiling with no measurable progress. Store the fingerprint history in task state.

Implementation contract:

```text
Implement no-progress decision
Return `retry` on first failure, `diagnose` on second unchanged failure, and `blocked` after the configured ceiling with no measurable progress. Store the fingerprint history in task state.
```


- [ ] **Step 5: Run failure tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_failures -v`

Expected: PASS.

- [ ] **Step 6: Commit failure memory**

Run: `git add src/nexus_harness/failures.py tests/test_failures.py && git commit -m "feat: stop unchanged retry loops"`.

---

### Task 7: Implement completion gate and acceptance promotion

**Files:**
- Create: `src/nexus_harness/completion.py`
- Create: `tests/test_completion.py`

**Interfaces:**
- Consumes: Task state, evidence ledger, quality/security reports, review findings and current diff hash.
- Produces: Deterministic `CompletionResult` used by hooks and CLI.

- [ ] **Step 1: Write failing false-done test**

Create `tests/test_completion.py`:

```python
import unittest
from nexus_harness.completion import evaluate_completion

class CompletionTests(unittest.TestCase):
    def test_failing_acceptance_blocks_done(self):
        state = {
            "tracking_required": True,
            "issue": 123,
            "acceptance": [{"id": "AC-1", "status": "FAIL"}],
            "quality_gate": "PASS",
            "security_gate": "PASS",
            "review_gate": "PASS",
            "current_diff_hash": "abc"
        }
        result = evaluate_completion(state)
        self.assertEqual(result.status, "FAIL")
        self.assertIn("acceptance", result.reasons[0])
```

- [ ] **Step 2: Run completion test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_completion -v`

Expected: import failure.

- [ ] **Step 3: Implement acceptance promotion from evidence**

Add `promote_acceptance(state, evidence)` that only marks a criterion `PASS` when the referenced evidence exists, exit code is 0 and `diff_hash` equals `current_diff_hash`.

Implementation contract:

```text
Implement acceptance promotion from evidence
Add `promote_acceptance(state, evidence)` that only marks a criterion `PASS` when the referenced evidence exists, exit code is 0 and `diff_hash` equals `current_diff_hash`.
```


- [ ] **Step 4: Implement completion evaluation**

Require linked Issue when tracking is required, all acceptance PASS, quality/security PASS, review PASS or justified SKIP, no confirmed blocker/high finding, fresh evidence and matching reviewed/verified diff hash.

Implementation contract:

```text
Implement completion evaluation
Require linked Issue when tracking is required, all acceptance PASS, quality/security PASS, review PASS or justified SKIP, no confirmed blocker/high finding, fresh evidence and matching reviewed/verified diff hash.
```


- [ ] **Step 5: Run completion tests**

Add stale-evidence and high-finding test cases. Run: `PYTHONPATH=src python3 -m unittest tests.test_completion -v`.

Expected: PASS.

- [ ] **Step 6: Commit completion gate**

Run: `git add src/nexus_harness/completion.py tests/test_completion.py && git commit -m "feat: block false task completion"`.

---

### Task 8: Add end-to-end workflow integration test

**Files:**
- Create: `tests/test_workflow_integration.py`

**Interfaces:**
- Consumes: All Plan 2 components.
- Produces: One executable proof that a task moves from classification to `READY_TO_SHIP` and rejects stale evidence.

- [ ] **Step 1: Write the integration scenario**

Create `tests/test_workflow_integration.py` with a scenario that:
1. creates a mutable task;
2. links Issue `123`;
3. adds `AC-001` as FAIL;
4. creates independent frontend/backend graph nodes;
5. records passing verification for diff `abc`;
6. promotes acceptance;
7. records quality/security/review PASS;
8. evaluates completion as `READY_TO_SHIP`;
9. changes current diff to `def`;
10. verifies completion returns FAIL due to stale evidence.

Implementation contract:

```text
Write the integration scenario
Create `tests/test_workflow_integration.py` with a scenario that: 1. creates a mutable task; 2. links Issue `123`; 3. adds `AC-001` as FAIL; 4. creates independent frontend/backend graph nodes; 5. records passing verification for diff `abc`; 6. promotes acceptance; 7. records quality/security/review PASS; 8. evaluates completion as `READY_TO_SHIP`; 9. changes current diff to `def`; 10. verifies completion returns FAIL due to stale evidence.
```


- [ ] **Step 2: Run the integration test**

Run: `PYTHONPATH=src python3 -m unittest tests.test_workflow_integration -v`

Expected: PASS.

- [ ] **Step 3: Run the complete Plan 2 suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v` and `scripts/validate`.

Expected: PASS.

- [ ] **Step 4: Commit Plan 2 completion**

Run: `git add tests/test_workflow_integration.py && git commit -m "test: prove nexus workflow quality gates"`.

---
