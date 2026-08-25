# Nexus Harness v4 — PostHog Incident Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use PostHog Cloud as the single product/runtime analytics service and turn meaningful runtime regressions into deduplicated GitHub work items.

**Architecture:** The harness standardizes release metadata, normalizes PostHog problems, applies an actionable-incident threshold, deduplicates against open Issues, and verifies runtime after deployment without introducing a second observability SaaS.

**Tech Stack:** Python 3.11+, PostHog Cloud/API, GitHub Issues/Projects

**Spec:** `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`

## Global Constraints

- Python runtime floor is 3.11 so TOML is parsed with the standard-library `tomllib` module.
- Canonical machine configuration uses TOML/JSON; no YAML parser is introduced into the harness runtime.
- The original `nexus-harness-export-20260825-094238.tar.gz` is immutable; all destructive cleanup occurs only in a v4 working copy.
- No project-specific IP, SSH target, absolute project path, client secret or model name belongs in `core/constitution.md`.
- Generated `dist/` content is never edited by hand; drift is a validation failure.
- Tests use Python standard-library `unittest` unless a target project already has its own test runner.
- Every implementation task is performed test-first where behavior can be isolated.
- PostHog is the only baseline product/runtime analytics SaaS.
- Raw events are aggregated before GitHub Issue creation.
- PostHog API credentials never enter source control or generated runtime prompts.
- Session replay/instrumentation follows data-minimization and masking defaults.
- Unknown runtime/root-cause facts remain explicitly unknown until evidence exists.

---

## File Structure

- `src/nexus_harness/posthog.py` — safe PostHog API/config boundary
- `src/nexus_harness/observability.py` — release context
- `src/nexus_harness/incidents.py` — problem normalization/fingerprints
- `src/nexus_harness/incident_policy.py` — actionability/dedupe decision
- `src/nexus_harness/incident_issue.py` — GitHub Issue bridge
- `src/nexus_harness/postdeploy.py` — runtime verification

---

### Task 1: Define PostHog configuration and privacy boundary

**Files:**
- Create: `core/observability/posthog.toml`
- Create: `src/nexus_harness/posthog.py`
- Create: `tests/test_posthog_config.py`

**Interfaces:**
- Consumes: PostHog Cloud project identifiers/API credentials supplied outside source control.
- Produces: Project/runtime PostHog configuration with hard spend/privacy constraints and no secret leakage.

- [ ] **Step 1: Write failing PostHog config test**

Create `tests/test_posthog_config.py`:

```python
import unittest
from nexus_harness.posthog import PostHogConfig

class PostHogConfigTests(unittest.TestCase):
    def test_personal_api_key_is_never_serialized(self):
        cfg = PostHogConfig(project_id="123", host="https://us.posthog.com", personal_api_key="secret")
        self.assertNotIn("secret", cfg.safe_dict().values())
```

- [ ] **Step 2: Run config test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_posthog_config -v`

Expected: import failure.

- [ ] **Step 3: Implement safe PostHog configuration**

Load host/project identifiers from project profile and personal API token from environment/secret store only. `safe_dict()` must redact credentials. Define a spend-policy flag requiring a hard PostHog billing cap/free-tier preference before runtime automation is enabled.

Implementation contract:

```text
Implement safe PostHog configuration
Load host/project identifiers from project profile and personal API token from environment/secret store only. `safe_dict()` must redact credentials. Define a spend-policy flag requiring a hard PostHog billing cap/free-tier preference before runtime automation is enabled.
```


- [ ] **Step 4: Define data-minimization defaults**

Document that passwords, auth tokens, payment data, raw sensitive form fields and client secrets are never captured. Session replay masking defaults must be enabled unless a project explicitly proves a narrower safe configuration.

Implementation contract:

```text
Define data-minimization defaults
Document that passwords, auth tokens, payment data, raw sensitive form fields and client secrets are never captured. Session replay masking defaults must be enabled unless a project explicitly proves a narrower safe configuration.
```


- [ ] **Step 5: Run PostHog config tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_posthog_config -v`

Expected: PASS.

- [ ] **Step 6: Commit PostHog config boundary**

Run: `git add core/observability src/nexus_harness/posthog.py tests/test_posthog_config.py && git commit -m "feat: configure posthog observability boundary"`.

---

### Task 2: Implement project instrumentation checklist and release identity

**Files:**
- Create: `templates/posthog/INSTRUMENTATION.md`
- Create: `src/nexus_harness/observability.py`
- Create: `tests/test_observability.py`

**Interfaces:**
- Consumes: Project profile, release Git SHA and immutable deploy digest.
- Produces: Consistent event/error/session metadata and release correlation without a second observability platform.

- [ ] **Step 1: Write failing release-context test**

Create `tests/test_observability.py`:

```python
import unittest
from nexus_harness.observability import release_context

class ObservabilityTests(unittest.TestCase):
    def test_release_context_contains_commit_and_environment(self):
        data = release_context("abc123", "production", "sdr-platform")
        self.assertEqual(data["release"], "abc123")
        self.assertEqual(data["environment"], "production")
        self.assertEqual(data["project"], "sdr-platform")
```

- [ ] **Step 2: Run observability test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_observability -v`

Expected: import failure.

- [ ] **Step 3: Implement release context contract**

Standardize metadata keys: `project`, `environment`, `release`, `deployment_digest`, `tenant/client pseudonymous identifier`, `route/feature`, and `trace/session identifiers` when available. Never include secrets or unrestricted PII.

Implementation contract:

```text
Implement release context contract
Standardize metadata keys: `project`, `environment`, `release`, `deployment_digest`, `tenant/client pseudonymous identifier`, `route/feature`, and `trace/session identifiers` when available. Never include secrets or unrestricted PII.
```


- [ ] **Step 4: Create instrumentation checklist**

The template requires product events for meaningful user actions, error tracking initialization, session replay with privacy masking, release identity injection and verification that development/staging traffic is distinguishable from production.

Implementation contract:

```text
Create instrumentation checklist
The template requires product events for meaningful user actions, error tracking initialization, session replay with privacy masking, release identity injection and verification that development/staging traffic is distinguishable from production.
```


- [ ] **Step 5: Run observability tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_observability -v`

Expected: PASS.

- [ ] **Step 6: Commit instrumentation contract**

Run: `git add templates/posthog src/nexus_harness/observability.py tests/test_observability.py && git commit -m "feat: standardize posthog release context"`.

---

### Task 3: Normalize PostHog runtime problems into incident candidates

**Files:**
- Create: `src/nexus_harness/incidents.py`
- Create: `tests/fixtures/posthog-errors.json`
- Create: `tests/test_incidents.py`

**Interfaces:**
- Consumes: PostHog API error/runtime records and project identity.
- Produces: `IncidentCandidate` objects with stable fingerprint, severity inputs and evidence links.

- [ ] **Step 1: Write failing incident normalization test**

Create `tests/test_incidents.py`:

```python
import json
import unittest
from pathlib import Path
from nexus_harness.incidents import normalize_posthog_problem

class IncidentTests(unittest.TestCase):
    def test_same_error_location_has_stable_fingerprint(self):
        payload = json.loads(Path("tests/fixtures/posthog-errors.json").read_text())
        a = normalize_posthog_problem(payload[0])
        b = normalize_posthog_problem(payload[1])
        self.assertEqual(a.fingerprint, b.fingerprint)
```

- [ ] **Step 2: Create PostHog problem fixture**

Create `tests/fixtures/posthog-errors.json` with two occurrences of the same normalized exception/release path but different timestamps/session IDs, so deduplication can be tested without depending on live PostHog.

Implementation contract:

```text
Create PostHog problem fixture
Create `tests/fixtures/posthog-errors.json` with two occurrences of the same normalized exception/release path but different timestamps/session IDs, so deduplication can be tested without depending on live PostHog.
```


- [ ] **Step 3: Run incident test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_incidents -v`

Expected: import failure.

- [ ] **Step 4: Implement normalized incident candidates**

Fingerprint stable fields such as project, environment, error type, normalized stack location and route/feature. Keep occurrence count, affected-user count, first/last seen, release and PostHog IDs as evidence but exclude volatile values from the fingerprint.

Implementation contract:

```text
Implement normalized incident candidates
Fingerprint stable fields such as project, environment, error type, normalized stack location and route/feature. Keep occurrence count, affected-user count, first/last seen, release and PostHog IDs as evidence but exclude volatile values from the fingerprint.
```


- [ ] **Step 5: Run incident normalization tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_incidents -v`

Expected: PASS.

- [ ] **Step 6: Commit incident normalization**

Run: `git add src/nexus_harness/incidents.py tests/test_incidents.py tests/fixtures/posthog-errors.json && git commit -m "feat: normalize posthog runtime problems"`.

---

### Task 4: Implement deduplication and actionable-incident policy

**Files:**
- Create: `core/observability/incidents.toml`
- Create: `src/nexus_harness/incident_policy.py`
- Create: `tests/test_incident_policy.py`

**Interfaces:**
- Consumes: Incident candidates and existing open GitHub Issues.
- Produces: Decision `ignore`, `update_existing`, or `create_issue` with severity.

- [ ] **Step 1: Write failing incident-policy tests**

Create `tests/test_incident_policy.py`:

```python
import unittest
from nexus_harness.incident_policy import classify_incident

class IncidentPolicyTests(unittest.TestCase):
    def test_single_low_impact_occurrence_is_not_issue(self):
        result = classify_incident(occurrences=1, affected_users=1, regression=False, fatal=False)
        self.assertEqual(result.action, "ignore")

    def test_release_regression_creates_issue(self):
        result = classify_incident(occurrences=4, affected_users=3, regression=True, fatal=False)
        self.assertEqual(result.action, "create_issue")
```

- [ ] **Step 2: Run incident-policy tests and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_incident_policy -v`

Expected: import failure.

- [ ] **Step 3: Implement simple budget-first incident rules**

Prioritize release regressions, fatal/high-impact errors, repeated errors crossing configured occurrence/user thresholds, and security-adjacent runtime failures. Ignore isolated low-impact events unless manually promoted.

Implementation contract:

```text
Implement simple budget-first incident rules
Prioritize release regressions, fatal/high-impact errors, repeated errors crossing configured occurrence/user thresholds, and security-adjacent runtime failures. Ignore isolated low-impact events unless manually promoted.
```


- [ ] **Step 4: Implement open-Issue deduplication**

Before `create_issue`, search open Issues for the incident fingerprint stored in a hidden/structured body marker. If found, add/update evidence instead of creating a duplicate.

Implementation contract:

```text
Implement open-Issue deduplication
Before `create_issue`, search open Issues for the incident fingerprint stored in a hidden/structured body marker. If found, add/update evidence instead of creating a duplicate.
```


- [ ] **Step 5: Run incident-policy tests**

Add duplicate-Issue and threshold cases; run tests and expect PASS.

- [ ] **Step 6: Commit incident policy**

Run: `git add core/observability/incidents.toml src/nexus_harness/incident_policy.py tests/test_incident_policy.py && git commit -m "feat: triage runtime incidents"`.

---

### Task 5: Create GitHub Issues from actionable runtime incidents

**Files:**
- Create: `src/nexus_harness/incident_issue.py`
- Create: `tests/test_incident_issue.py`

**Interfaces:**
- Consumes: Actionable incident decision, GitHub governance client and Issue Contract.
- Produces: Deduplicated runtime-derived Bug/Incident Issue with PostHog evidence and release identity.

- [ ] **Step 1: Write failing runtime-Issue body test**

Create `tests/test_incident_issue.py` asserting the generated Issue body includes:
- project/environment;
- release SHA;
- occurrence/affected-user counts;
- PostHog problem/session identifiers when available;
- initial acceptance/reproduction section;
- incident fingerprint marker;
and does not include the PostHog personal API token.

Implementation contract:

```text
Write failing runtime-Issue body test
Create `tests/test_incident_issue.py` asserting the generated Issue body includes: - project/environment; - release SHA; - occurrence/affected-user counts; - PostHog problem/session identifiers when available; - initial acceptance/reproduction section; - incident fingerprint marker; and does not include the PostHog personal API token.
```


- [ ] **Step 2: Run runtime-Issue test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_incident_issue -v`

Expected: missing renderer.

- [ ] **Step 3: Implement runtime Issue renderer**

Use Type `bug` or `incident`, map severity to project priority, link PostHog evidence IDs and release, and state that root/escape cause remain `unknown until diagnosis` as a factual state field rather than pretending they are already known.

Implementation contract:

```text
Implement runtime Issue renderer
Use Type `bug` or `incident`, map severity to project priority, link PostHog evidence IDs and release, and state that root/escape cause remain `unknown until diagnosis` as a factual state field rather than pretending they are already known.
```


- [ ] **Step 4: Create or update through GitHub boundary**

Call the Plan 5 GitHub client. New Issues enter `Inbox`; duplicates receive a new evidence comment/update and retain the original Issue number.

Implementation contract:

```text
Create or update through GitHub boundary
Call the Plan 5 GitHub client. New Issues enter `Inbox`; duplicates receive a new evidence comment/update and retain the original Issue number.
```


- [ ] **Step 5: Run runtime-Issue tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_incident_issue -v`

Expected: PASS.

- [ ] **Step 6: Commit incident→Issue bridge**

Run: `git add src/nexus_harness/incident_issue.py tests/test_incident_issue.py && git commit -m "feat: turn actionable runtime errors into issues"`.

---

### Task 6: Implement post-deploy runtime verification

**Files:**
- Create: `src/nexus_harness/postdeploy.py`
- Create: `tests/test_postdeploy.py`

**Interfaces:**
- Consumes: Deployment manifest, health/smoke results and PostHog runtime query results.
- Produces: Post-deploy verification that can close the Issue or trigger rollback/incident.

- [ ] **Step 1: Write failing regression-verification test**

Create `tests/test_postdeploy.py`:

```python
import unittest
from nexus_harness.postdeploy import evaluate_postdeploy

class PostDeployTests(unittest.TestCase):
    def test_new_release_error_regression_fails_verification(self):
        result = evaluate_postdeploy(health=True, smoke=True, new_error_regression=True)
        self.assertEqual(result.gate, "FAIL")
```

- [ ] **Step 2: Run postdeploy test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_postdeploy -v`

Expected: import failure.

- [ ] **Step 3: Implement post-deploy evaluator**

Require health and smoke PASS. When PostHog data is available inside the configured observation window, a newly detected high-severity release regression fails verification; absence of enough data is `INSUFFICIENT_DATA`, not falsely reported as clean.

Implementation contract:

```text
Implement post-deploy evaluator
Require health and smoke PASS. When PostHog data is available inside the configured observation window, a newly detected high-severity release regression fails verification; absence of enough data is `INSUFFICIENT_DATA`, not falsely reported as clean.
```


- [ ] **Step 4: Connect result to lifecycle**

PASS allows Stage 9 to close the linked Issue. FAIL creates/updates an incident and follows rollback policy. INSUFFICIENT_DATA leaves deployment successful but records the limitation without inventing confidence.

- [ ] **Step 5: Run postdeploy tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_postdeploy -v`

Expected: PASS.

- [ ] **Step 6: Commit post-deploy verification**

Run: `git add src/nexus_harness/postdeploy.py tests/test_postdeploy.py && git commit -m "feat: verify runtime after deployment"`.

---

### Task 7: Run PostHog incident integration test

**Files:**
- Create: `tests/test_incident_integration.py`

**Interfaces:**
- Consumes: PostHog config, incident normalization/policy, GitHub governance and post-deploy evaluation.
- Produces: Proof that repeated release regression becomes one tracked GitHub Issue and can be closed after a verified fix.

- [ ] **Step 1: Create mocked incident lifecycle scenario**

Simulate three occurrences of the same release regression, assert one Issue creation; simulate two more occurrences and assert update of the same Issue; simulate a fixed release with health/smoke PASS and no confirmed regression and assert lifecycle can close the Issue.

Implementation contract:

```text
Create mocked incident lifecycle scenario
Simulate three occurrences of the same release regression, assert one Issue creation; simulate two more occurrences and assert update of the same Issue; simulate a fixed release with health/smoke PASS and no confirmed regression and assert lifecycle can close the Issue.
```


- [ ] **Step 2: Run incident integration test**

Run: `PYTHONPATH=src python3 -m unittest tests.test_incident_integration -v`

Expected: PASS.

- [ ] **Step 3: Run Plan 7 full verification**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v && scripts/validate`.

Expected: PASS.

- [ ] **Step 4: Commit Plan 7 completion**

Run: `git add tests/test_incident_integration.py && git commit -m "test: prove posthog incident lifecycle"`.

---
