# Nexus Harness v4 — GitHub Project Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make GitHub Issues, PRs and one central Project the operational system of record for all managed projects while keeping the process lightweight for a solo developer.

**Architecture:** The harness resolves project identity, creates or links the minimum necessary Issue hierarchy, enforces Issue↔PR contracts and synchronizes lifecycle/quality/security state to a central GitHub Project automatically.

**Tech Stack:** Python 3.11+, GitHub CLI/API/GraphQL, GitHub Issues, Projects and PRs

**Spec:** `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`

## Global Constraints

- Python runtime floor is 3.11 so TOML is parsed with the standard-library `tomllib` module.
- Canonical machine configuration uses TOML/JSON; no YAML parser is introduced into the harness runtime.
- The original `nexus-harness-export-20260825-094238.tar.gz` is immutable; all destructive cleanup occurs only in a v4 working copy.
- No project-specific IP, SSH target, absolute project path, client secret or model name belongs in `core/constitution.md`.
- Generated `dist/` content is never edited by hand; drift is a validation failure.
- Tests use Python standard-library `unittest` unless a target project already has its own test runner.
- Every implementation task is performed test-first where behavior can be isolated.
- Mutable corrections, improvements and features require a GitHub Issue before implementation.
- Read-only inspection/research does not create an Issue by default.
- A bounded bug should not create Epic/Story/Task ceremony unless independent deliverables justify it.
- GitHub remains the only work-tracking source of truth; Jira/Linear/Trello/Slack are not baseline dependencies.

---

## File Structure

- `projects.toml` — cross-repository identity registry
- `src/nexus_harness/github.py` — GitHub API boundary
- `src/nexus_harness/tracking.py` — Issue tracking gate
- `src/nexus_harness/hierarchy.py` — minimal hierarchy decisions
- `src/nexus_harness/pull_request.py` — PR contract and readiness
- `src/nexus_harness/project_sync.py` — central Project synchronization
- `src/nexus_harness/project_doc.py` — PROJECT.md generation

---

### Task 1: Create project registry and repository identity

**Files:**
- Create: `src/nexus_harness/project.py`
- Create: `tests/test_project_registry.py`
- Create: `core/project/registry.schema.json`
- Create: `projects.toml`

**Interfaces:**
- Consumes: Repository remotes/current directory and explicit project profile.
- Produces: Canonical project identity used by task state, Issues, PRs, CI and observability.

- [ ] **Step 1: Write failing registry lookup test**

Create `tests/test_project_registry.py`:

```python
import unittest
from nexus_harness.project import ProjectRegistry

class ProjectRegistryTests(unittest.TestCase):
    def test_repository_resolves_project(self):
        registry = ProjectRegistry.from_dict({
            "projects": {
                "sdr-platform": {
                    "repository": "Rubens-Marques/SDR-Plataform",
                    "client": "vuca",
                    "status": "active"
                }
            }
        })
        project = registry.by_repository("Rubens-Marques/SDR-Plataform")
        self.assertEqual(project.id, "sdr-platform")
```

- [ ] **Step 2: Run registry test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_project_registry -v`

Expected: missing registry implementation.

- [ ] **Step 3: Implement project registry**

Implement immutable `Project` records and lookups by project ID/repository. Registry validation rejects duplicate repository mappings and missing status/client fields.

Implementation contract:

```text
Implement project registry
Implement immutable `Project` records and lookups by project ID/repository. Registry validation rejects duplicate repository mappings and missing status/client fields.
```


- [ ] **Step 4: Seed known projects without secrets**

Create `projects.toml` with non-secret identity only:

```toml
[projects.sdr-platform]
name = "SDR Platform"
repository = "Rubens-Marques/SDR-Plataform"
client = "vuca"
status = "active"

[projects.marketing-hub]
name = "Marketing Hub"
repository = "NexusDataBI/marketing-hub"
client = "nexus"
status = "active"
```

Do not place VM IPs or API keys here.

- [ ] **Step 5: Run registry tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_project_registry -v`

Expected: PASS.

- [ ] **Step 6: Commit registry**

Run: `git add src/nexus_harness/project.py tests/test_project_registry.py core/project/registry.schema.json projects.toml && git commit -m "feat: add nexus project registry"`.

---

### Task 2: Implement GitHub CLI/API boundary

**Files:**
- Create: `src/nexus_harness/github.py`
- Create: `tests/test_github.py`

**Interfaces:**
- Consumes: Authenticated `gh` CLI on local/CI environments.
- Produces: Typed wrappers for Issue, PR and Project operations with testable subprocess boundaries.

- [ ] **Step 1: Write failing GitHub wrapper test**

Create `tests/test_github.py`:

```python
import unittest
from unittest.mock import patch
from nexus_harness.github import GitHub

class GitHubTests(unittest.TestCase):
    @patch("nexus_harness.github.subprocess.run")
    def test_issue_create_uses_json_output(self, run):
        run.return_value.stdout = '{"number":123,"url":"https://github.com/x/y/issues/123"}'
        run.return_value.returncode = 0
        issue = GitHub().create_issue("x/y", "Bug: example", "body", ["type:bug"])
        self.assertEqual(issue.number, 123)
```

- [ ] **Step 2: Run GitHub wrapper test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_github -v`

Expected: import failure.

- [ ] **Step 3: Implement safe `gh` command execution**

Implement a subprocess wrapper that passes arguments as a list, never shell-concatenates user content, captures JSON and redacts tokens from errors. Add `create_issue`, `edit_issue`, `create_pr`, `view_pr`, `api_graphql` and `project_item_update` methods.

Implementation contract:

```text
Implement safe `gh` command execution
Implement a subprocess wrapper that passes arguments as a list, never shell-concatenates user content, captures JSON and redacts tokens from errors. Add `create_issue`, `edit_issue`, `create_pr`, `view_pr`, `api_graphql` and `project_item_update` methods.
```


- [ ] **Step 4: Run GitHub wrapper tests**

Add a non-zero exit test and ensure the raised exception includes the GitHub error but no environment values. Run tests and expect PASS.

- [ ] **Step 5: Commit GitHub boundary**

Run: `git add src/nexus_harness/github.py tests/test_github.py && git commit -m "feat: add github governance client"`.

---

### Task 3: Implement Issue Contract and tracking gate

**Files:**
- Create: `core/project/issue-contract.md`
- Create: `src/nexus_harness/tracking.py`
- Create: `tests/test_tracking.py`

**Interfaces:**
- Consumes: Task classification, project identity and GitHub client.
- Produces: Create/find/link Issue before implementation-bearing work.

- [ ] **Step 1: Write failing tracking-gate tests**

Create `tests/test_tracking.py`:

```python
import unittest
from nexus_harness.tracking import tracking_required

class TrackingTests(unittest.TestCase):
    def test_change_requires_issue(self):
        self.assertTrue(tracking_required("change", mutable=True))

    def test_read_only_inspect_does_not_require_issue(self):
        self.assertFalse(tracking_required("inspect", mutable=False))
```

- [ ] **Step 2: Run tracking tests and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_tracking -v`

Expected: import failure.

- [ ] **Step 3: Define Issue body contract**

`core/project/issue-contract.md` requires:

```text
Summary
Type
Priority
Project/Area
Problem or desired outcome
Acceptance Criteria
Risk/Environment
Evidence links when bug/incident
Dependencies
```

For a confirmed bug append Reproduction, Proximate Cause, Root Cause, Escape Cause, Regression Guard and Preventive Control where applicable.

- [ ] **Step 4: Implement create-or-link behavior**

If task state already has an Issue, validate it is open/relevant. Otherwise search the repository for an open Issue containing the task fingerprint/title before creating a duplicate. Store Issue number/URL in task state.

Implementation contract:

```text
Implement create-or-link behavior
If task state already has an Issue, validate it is open/relevant. Otherwise search the repository for an open Issue containing the task fingerprint/title before creating a duplicate. Store Issue number/URL in task state.
```


- [ ] **Step 5: Run tracking tests**

Add mocked create/search cases and run `PYTHONPATH=src python3 -m unittest tests.test_tracking -v`.

Expected: PASS.

- [ ] **Step 6: Commit tracking gate**

Run: `git add core/project/issue-contract.md src/nexus_harness/tracking.py tests/test_tracking.py && git commit -m "feat: require github issue tracking"`.

---

### Task 4: Implement hierarchy rules for Epics, Features, Bugs and Tasks

**Files:**
- Create: `src/nexus_harness/hierarchy.py`
- Create: `tests/test_hierarchy.py`

**Interfaces:**
- Consumes: Task scope/type and GitHub sub-issue APIs.
- Produces: Minimal hierarchy decisions that avoid Jira-style ceremony.

- [ ] **Step 1: Write failing hierarchy test**

Create `tests/test_hierarchy.py`:

```python
import unittest
from nexus_harness.hierarchy import tracking_shape

class HierarchyTests(unittest.TestCase):
    def test_bounded_bug_is_single_issue(self):
        shape = tracking_shape(scope="bounded", work_type="bug")
        self.assertEqual(shape, ("bug",))

    def test_architectural_feature_can_have_epic_and_tasks(self):
        shape = tracking_shape(scope="architectural", work_type="feature")
        self.assertEqual(shape, ("epic", "feature", "task"))
```

- [ ] **Step 2: Run hierarchy tests and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_hierarchy -v`

Expected: import failure.

- [ ] **Step 3: Implement ceremony-minimizing hierarchy policy**

Use one Issue for bounded bugs/improvements by default. Use Epic → Feature/Story → Task only for architectural/long-horizon work where independent deliverables exist. Never create an empty child Issue solely to satisfy hierarchy.

Implementation contract:

```text
Implement ceremony-minimizing hierarchy policy
Use one Issue for bounded bugs/improvements by default. Use Epic → Feature/Story → Task only for architectural/long-horizon work where independent deliverables exist. Never create an empty child Issue solely to satisfy hierarchy.
```


- [ ] **Step 4: Implement GitHub sub-issue linking**

Use GitHub's sub-issue relationship through `gh api graphql` when hierarchy is selected. Persist parent/child numbers in task state so runtime adapters do not need to rediscover them.

Implementation contract:

```text
Implement GitHub sub-issue linking
Use GitHub's sub-issue relationship through `gh api graphql` when hierarchy is selected. Persist parent/child numbers in task state so runtime adapters do not need to rediscover them.
```


- [ ] **Step 5: Run hierarchy tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_hierarchy -v`

Expected: PASS.

- [ ] **Step 6: Commit hierarchy policy**

Run: `git add src/nexus_harness/hierarchy.py tests/test_hierarchy.py && git commit -m "feat: map work into github issue hierarchy"`.

---

### Task 5: Implement PR Contract and merge readiness

**Files:**
- Create: `core/project/pr-contract.md`
- Create: `src/nexus_harness/pull_request.py`
- Create: `tests/test_pull_request.py`

**Interfaces:**
- Consumes: Issue, acceptance state, quality/security reports and current branch.
- Produces: PR body generation and READY_TO_MERGE gate.

- [ ] **Step 1: Write failing PR-link test**

Create `tests/test_pull_request.py`:

```python
import unittest
from nexus_harness.pull_request import render_pr_body

class PullRequestTests(unittest.TestCase):
    def test_complete_issue_uses_closes_reference(self):
        body = render_pr_body(issue=123, partial=False, summary="Fix", evidence=[])
        self.assertIn("Closes #123", body)
```

- [ ] **Step 2: Run PR test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_pull_request -v`

Expected: import failure.

- [ ] **Step 3: Define PR contract**

PR body contains Summary, linked Issue, Scope, Acceptance status, Verification, Quality/Security summary, Screenshots for frontend when required, Deployment impact and Known limitations. Use `Closes #N` only when the PR fully resolves the Issue; otherwise `Refs #N`.

Implementation contract:

```text
Define PR contract
PR body contains Summary, linked Issue, Scope, Acceptance status, Verification, Quality/Security summary, Screenshots for frontend when required, Deployment impact and Known limitations. Use `Closes #N` only when the PR fully resolves the Issue; otherwise `Refs #N`.
```


- [ ] **Step 4: Implement merge-readiness checks**

Block ready/merge when Issue missing, acceptance incomplete, quality/security gate failed, blocker/high finding exists or required evidence is stale. Draft PRs may exist before all checks are green.

Implementation contract:

```text
Implement merge-readiness checks
Block ready/merge when Issue missing, acceptance incomplete, quality/security gate failed, blocker/high finding exists or required evidence is stale. Draft PRs may exist before all checks are green.
```


- [ ] **Step 5: Run PR contract tests**

Add partial PR (`Refs`) and failed-quality blocking tests. Run and expect PASS.

- [ ] **Step 6: Commit PR governance**

Run: `git add core/project/pr-contract.md src/nexus_harness/pull_request.py tests/test_pull_request.py && git commit -m "feat: enforce pr issue contract"`.

---

### Task 6: Synchronize lifecycle status to the central GitHub Project

**Files:**
- Create: `core/project/project-fields.toml`
- Create: `src/nexus_harness/project_sync.py`
- Create: `tests/test_project_sync.py`

**Interfaces:**
- Consumes: Task lifecycle state and GitHub Project ID/config.
- Produces: Automatic Project field/status updates without a second manual truth.

- [ ] **Step 1: Write failing status-mapping test**

Create `tests/test_project_sync.py`:

```python
import unittest
from nexus_harness.project_sync import lifecycle_to_project_status

class ProjectSyncTests(unittest.TestCase):
    def test_stage_5_maps_to_in_progress(self):
        self.assertEqual(lifecycle_to_project_status(5, "PASS"), "In Progress")

    def test_blocked_maps_to_blocked(self):
        self.assertEqual(lifecycle_to_project_status(6, "BLOCKED"), "Blocked")
```

- [ ] **Step 2: Run project-sync tests and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_project_sync -v`

Expected: import failure.

- [ ] **Step 3: Define central Project fields**

Configure `Nexus Engineering` fields: Project, Type, Status, Priority, Area, Client, Iteration, Risk, Environment, Quality, Security, Target date. Initial owner is `Rubens-Marques`; the project ID is stored in local/user configuration rather than core source.

Implementation contract:

```text
Define central Project fields
Configure `Nexus Engineering` fields: Project, Type, Status, Priority, Area, Client, Iteration, Risk, Environment, Quality, Security, Target date. Initial owner is `Rubens-Marques`; the project ID is stored in local/user configuration rather than core source.
```


- [ ] **Step 4: Implement lifecycle mapping**

Map Issue creation→Inbox, acceptance ready→Ready, Stage 5→In Progress, PR→Review, gate failure→Blocked, post-merge verification→Verifying and successful finish→Done. Update Quality/Security fields from report gates.

Implementation contract:

```text
Implement lifecycle mapping
Map Issue creation→Inbox, acceptance ready→Ready, Stage 5→In Progress, PR→Review, gate failure→Blocked, post-merge verification→Verifying and successful finish→Done. Update Quality/Security fields from report gates.
```


- [ ] **Step 5: Run project sync tests**

Use mocked GraphQL calls and verify only changed fields are sent. Run tests and expect PASS.

- [ ] **Step 6: Commit Project synchronization**

Run: `git add core/project/project-fields.toml src/nexus_harness/project_sync.py tests/test_project_sync.py && git commit -m "feat: sync lifecycle to github project"`.

---

### Task 7: Generate PROJECT.md for every managed repository

**Files:**
- Create: `src/nexus_harness/project_doc.py`
- Create: `tests/test_project_doc.py`
- Create: `templates/PROJECT.md`

**Interfaces:**
- Consumes: Project registry and project profile.
- Produces: Short agent-readable repository orientation document.

- [ ] **Step 1: Write failing PROJECT.md test**

Create `tests/test_project_doc.py` asserting generated Markdown includes project ID, repository, client/status, quality profile, canonical commands and observability ID, while excluding secrets and client VM IPs.

Implementation contract:

```text
Write failing PROJECT.md test
Create `tests/test_project_doc.py` asserting generated Markdown includes project ID, repository, client/status, quality profile, canonical commands and observability ID, while excluding secrets and client VM IPs.
```


- [ ] **Step 2: Run PROJECT.md test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_project_doc -v`

Expected: missing renderer.

- [ ] **Step 3: Implement deterministic project document**

Render sections Identity, GitHub, Current Focus, Runtime Profile, Quality, Observability, Commands and Architecture links. `Current Focus` may be refreshed from the open Epic/Feature selected in project state.

Implementation contract:

```text
Implement deterministic project document
Render sections Identity, GitHub, Current Focus, Runtime Profile, Quality, Observability, Commands and Architecture links. `Current Focus` may be refreshed from the open Epic/Feature selected in project state.
```


- [ ] **Step 4: Run PROJECT.md tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_project_doc -v`

Expected: PASS.

- [ ] **Step 5: Commit project docs**

Run: `git add src/nexus_harness/project_doc.py tests/test_project_doc.py templates/PROJECT.md && git commit -m "feat: generate project context docs"`.

---

### Task 8: Prove end-to-end tracking flow

**Files:**
- Create: `tests/test_governance_integration.py`

**Interfaces:**
- Consumes: Registry, Issue, hierarchy, PR and Project synchronization components.
- Produces: Mocked proof of user request → Issue → lifecycle status → PR → Done.

- [ ] **Step 1: Create mocked governance integration scenario**

Test a bounded bug in `Rubens-Marques/SDR-Plataform`: resolve project, create one Issue, mark Ready, move to In Progress, render a PR with `Closes #123`, mark Review, pass gates, mark Verifying then Done. Assert no Epic or extra Task Issue is created.

Implementation contract:

```text
Create mocked governance integration scenario
Test a bounded bug in `Rubens-Marques/SDR-Plataform`: resolve project, create one Issue, mark Ready, move to In Progress, render a PR with `Closes #123`, mark Review, pass gates, mark Verifying then Done. Assert no Epic or extra Task Issue is created.
```


- [ ] **Step 2: Run governance integration test**

Run: `PYTHONPATH=src python3 -m unittest tests.test_governance_integration -v`

Expected: PASS.

- [ ] **Step 3: Run Plan 5 full verification**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v && scripts/validate`.

Expected: PASS.

- [ ] **Step 4: Commit Plan 5 completion**

Run: `git add tests/test_governance_integration.py && git commit -m "test: prove github project governance flow"`.

---
