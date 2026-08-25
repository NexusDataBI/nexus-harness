# Nexus Harness v4 — CI VPS, Security & Docker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move expensive CI/quality/security compute to the personal VPS, run only affected checks/images, and deploy immutable artifacts to isolated client VMs.

**Architecture:** The GitHub workflow remains the control plane while the personal VPS is the self-hosted compute plane. The affected graph batches checks, Trivy is the single security scanner, Docker images are built once and deployed by digest through a restricted client-VM contract.

**Tech Stack:** GitHub Actions, self-hosted runner, Python 3.11+, Docker/BuildKit, GHCR, Biome, Vitest, Playwright, Trivy

**Spec:** `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`

## Global Constraints

- Python runtime floor is 3.11 so TOML is parsed with the standard-library `tomllib` module.
- Canonical machine configuration uses TOML/JSON; no YAML parser is introduced into the harness runtime.
- The original `nexus-harness-export-20260825-094238.tar.gz` is immutable; all destructive cleanup occurs only in a v4 working copy.
- No project-specific IP, SSH target, absolute project path, client secret or model name belongs in `core/constitution.md`.
- Generated `dist/` content is never edited by hand; drift is a validation failure.
- Tests use Python standard-library `unittest` unless a target project already has its own test runner.
- Every implementation task is performed test-first where behavior can be isolated.
- Normal private-repository PRs target zero GitHub-hosted compute minutes.
- The CI VPS must not hold standing unrestricted production credentials.
- Post-merge workflows build/promote affected artifacts; they do not blindly repeat the complete PR validation.
- Production images are identified by immutable digest, never by `latest`.

---

## File Structure

- `src/nexus_harness/affected.py` — changed-path impact resolution
- `src/nexus_harness/ci.py` — workflow rendering
- `src/nexus_harness/tooling.py` — minimal tool role mapping
- `src/nexus_harness/build.py` — affected image builds
- `src/nexus_harness/deploy_manifest.py` — immutable artifact contract
- `infra/ci-vps/` — personal CI host provisioning
- `infra/client-vm/` — restricted production deployment

---

### Task 1: Define per-repository CI profile and affected component graph

**Files:**
- Create: `core/ci/profile.schema.json`
- Create: `profiles/projects/sdr-platform.toml`
- Create: `src/nexus_harness/affected.py`
- Create: `tests/test_affected.py`

**Interfaces:**
- Consumes: Graph engine and known SDR monorepo boundaries.
- Produces: `AffectedPlan` that maps changed paths to checks and images without running the entire monorepo.

- [ ] **Step 1: Write failing affected-component tests**

Create `tests/test_affected.py`:

```python
import unittest
from nexus_harness.affected import Component, resolve_affected

class AffectedTests(unittest.TestCase):
    def test_web_change_does_not_build_server_image(self):
        components = [
            Component("web", ("apps/web/**",), checks=("web-test",), images=("web",)),
            Component("server", ("apps/server/**",), checks=("server-test",), images=("server",)),
        ]
        plan = resolve_affected(["apps/web/src/button.tsx"], components)
        self.assertEqual(plan.images, ("web",))
        self.assertNotIn("server", plan.components)
```

- [ ] **Step 2: Run affected test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_affected -v`

Expected: import failure.

- [ ] **Step 3: Implement glob-based affected resolver**

Implement `Component(name, paths, depends_on, checks, images)` and `resolve_affected(changed_paths, components)`. Include transitive dependents, so a design-system change can affect `web` without automatically affecting unrelated backend images.

Implementation contract:

```text
Implement glob-based affected resolver
Implement `Component(name, paths, depends_on, checks, images)` and `resolve_affected(changed_paths, components)`. Include transitive dependents, so a design-system change can affect `web` without automatically affecting unrelated backend images.
```


- [ ] **Step 4: Create the SDR Platform project profile**

Create `profiles/projects/sdr-platform.toml` with explicit component groups:

```toml
[project]
id = "sdr-platform"
repository = "Rubens-Marques/SDR-Plataform"

[components.web]
paths = ["apps/web/**", "design-system/**"]
checks = ["biome", "typecheck-web", "vitest-web", "playwright-web"]
images = ["web"]

[components.server]
paths = ["apps/server/**"]
checks = ["biome", "typecheck-server", "vitest-server", "trivy-source"]
images = ["server"]

[components.figma_worker]
paths = ["apps/server/Dockerfile.figma-worker", "apps/server/src/**/figma/**"]
checks = ["trivy-source"]
images = ["figma-worker"]
```

- [ ] **Step 5: Run affected tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_affected -v`

Expected: PASS.

- [ ] **Step 6: Commit affected graph**

Run: `git add core/ci profiles/projects/sdr-platform.toml src/nexus_harness/affected.py tests/test_affected.py && git commit -m "feat: resolve affected ci components"`.

---

### Task 2: Generate a single self-hosted Quality Gate workflow

**Files:**
- Create: `ci/workflow.template.yml`
- Create: `src/nexus_harness/ci.py`
- Create: `tests/test_ci_render.py`

**Interfaces:**
- Consumes: Affected plan and Plan 2 quality/security gate commands.
- Produces: One compact GitHub Actions workflow that batches cheap checks and targets the self-hosted Nexus runner.

- [ ] **Step 1: Write failing CI render test**

Create `tests/test_ci_render.py`:

```python
import unittest
from nexus_harness.ci import render_workflow

class CiRenderTests(unittest.TestCase):
    def test_workflow_uses_self_hosted_and_cancels_obsolete_prs(self):
        text = render_workflow()
        self.assertIn("self-hosted", text)
        self.assertIn("nexus-ci", text)
        self.assertIn("cancel-in-progress: true", text)
        self.assertNotIn("ubuntu-latest", text)
```

- [ ] **Step 2: Run CI render test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_ci_render -v`

Expected: import failure.

Implementation contract:

```text
Run CI render test and confirm RED
Run: `PYTHONPATH=src python3 -m unittest tests.test_ci_render -v` Expected: import failure.
```


- [ ] **Step 3: Implement workflow rendering**

Render triggers for PR lifecycle plus manual dispatch. Use `concurrency` keyed by repository + PR/ref with `cancel-in-progress: true`. The required PR job runs on `[self-hosted, nexus-ci]` and executes `nexus ci affected --base ... --head ...` followed by one batched quality command.

Implementation contract:

```text
Implement workflow rendering
Render triggers for PR lifecycle plus manual dispatch. Use `concurrency` keyed by repository + PR/ref with `cancel-in-progress: true`. The required PR job runs on `[self-hosted, nexus-ci]` and executes `nexus ci affected --base ... --head ...` followed by one batched quality command.
```


- [ ] **Step 4: Separate PR validation from post-merge build**

Render a post-merge job that consumes the affected image plan and builds only changed production images. Do not repeat the full PR validation when branch protection requires the passing PR Quality Gate for the merged commit.

- [ ] **Step 5: Run CI rendering tests**

Add assertions that the PR job does not push images and the post-merge build job does not rerun `nexus quality full`. Run the test suite and expect PASS.

Implementation contract:

```text
Run CI rendering tests
Add assertions that the PR job does not push images and the post-merge build job does not rerun `nexus quality full`. Run the test suite and expect PASS.
```


- [ ] **Step 6: Commit generated CI workflow**

Run: `git add ci/workflow.template.yml src/nexus_harness/ci.py tests/test_ci_render.py && git commit -m "feat: generate low-cost self-hosted ci"`.

Implementation contract:

```text
Commit generated CI workflow
Run: `git add ci/workflow.template.yml src/nexus_harness/ci.py tests/test_ci_render.py && git commit -m "feat: generate low-cost self-hosted ci"`.
```


---

### Task 3: Provision the personal VPS as a dedicated Nexus CI host

**Files:**
- Create: `infra/ci-vps/install.sh`
- Create: `infra/ci-vps/nexus-ci.service`
- Create: `infra/ci-vps/README.md`
- Create: `tests/test_ci_vps_files.py`

**Interfaces:**
- Consumes: Ubuntu VPS with sudo access and private-repository GitHub runner registration token supplied during installation.
- Produces: Dedicated `nexus-ci` user, isolated runner directory, bounded cache directories and host health checks.

- [ ] **Step 1: Write failing infra-file policy test**

Create `tests/test_ci_vps_files.py` that asserts `install.sh`:
- creates a `nexus-ci` system user;
- does not contain client IP addresses;
- does not embed GitHub tokens;
- creates `/var/lib/nexus-ci`;
- installs no analytics/observability SaaS agent.

Implementation contract:

```text
Write failing infra-file policy test
Create `tests/test_ci_vps_files.py` that asserts `install.sh`: - creates a `nexus-ci` system user; - does not contain client IP addresses; - does not embed GitHub tokens; - creates `/var/lib/nexus-ci`; - installs no analytics/observability SaaS agent.
```


- [ ] **Step 2: Run infra policy test and confirm RED**

Run: `python3 -m unittest tests.test_ci_vps_files -v`

Expected: missing infra files.

- [ ] **Step 3: Create idempotent CI-host installer**

Write `install.sh` to create `nexus-ci`, `/opt/nexus-runner`, `/var/lib/nexus-ci/{cache,artifacts,logs}`, install required OS packages, verify Docker/rootless prerequisites, and install the GitHub runner binary from a version supplied as an environment variable at execution time. The token is read from stdin/environment and never written into the repository.

Implementation contract:

```text
Create idempotent CI-host installer
Write `install.sh` to create `nexus-ci`, `/opt/nexus-runner`, `/var/lib/nexus-ci/{cache,artifacts,logs}`, install required OS packages, verify Docker/rootless prerequisites, and install the GitHub runner binary from a version supplied as an environment variable at execution time. The token is read from stdin/environment and never written into the repository.
```


- [ ] **Step 4: Create systemd service and health command**

Run the runner under `nexus-ci` and create `nexus ci-host doctor` checks for disk, memory, Docker/rootless availability, runner process and outbound GitHub connectivity.

Implementation contract:

```text
Create systemd service and health command
Run the runner under `nexus-ci` and create `nexus ci-host doctor` checks for disk, memory, Docker/rootless availability, runner process and outbound GitHub connectivity.
```


- [ ] **Step 5: Run infra-file policy tests**

Run: `python3 -m unittest tests.test_ci_vps_files -v`

Expected: PASS.

- [ ] **Step 6: Commit CI VPS provisioning**

Run: `git add infra/ci-vps tests/test_ci_vps_files.py && git commit -m "feat: provision nexus ci vps"`.

---

### Task 4: Create the minimal tool bootstrap for Biome, Vitest, Playwright and Trivy

**Files:**
- Create: `src/nexus_harness/tooling.py`
- Create: `tests/test_tooling.py`
- Create: `core/policies/tooling.toml`

**Interfaces:**
- Consumes: Project profile and existing project package manager.
- Produces: Idempotent detection/install guidance with exactly one primary tool per responsibility.

- [ ] **Step 1: Write failing tool policy test**

Create `tests/test_tooling.py`:

```python
import unittest
from nexus_harness.tooling import BASELINE_TOOLS

class ToolingTests(unittest.TestCase):
    def test_baseline_has_one_tool_per_role(self):
        self.assertEqual(BASELINE_TOOLS["lint"], "biome")
        self.assertEqual(BASELINE_TOOLS["unit_integration"], "vitest")
        self.assertEqual(BASELINE_TOOLS["e2e_visual"], "playwright")
        self.assertEqual(BASELINE_TOOLS["security"], "trivy")
```

- [ ] **Step 2: Run tool policy test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_tooling -v`

Expected: import failure.

- [ ] **Step 3: Implement tool detection without automatic duplication**

Detect existing package manager and configured tools. If ESLint/Jest/Cypress already exist, report migration status instead of blindly installing overlapping tools. New project bootstrap installs only Biome, Vitest and Playwright as dev dependencies and expects Trivy on the CI host.

Implementation contract:

```text
Implement tool detection without automatic duplication
Detect existing package manager and configured tools. If ESLint/Jest/Cypress already exist, report migration status instead of blindly installing overlapping tools. New project bootstrap installs only Biome, Vitest and Playwright as dev dependencies and expects Trivy on the CI host.
```


- [ ] **Step 4: Implement one-command quality execution contract**

Expose `nexus quality run --profile standard` that resolves project commands, captures JSON/coverage/test artifacts, invokes Trivy once with relevant scanners, then writes normalized quality/security reports.

Implementation contract:

```text
Implement one-command quality execution contract
Expose `nexus quality run --profile standard` that resolves project commands, captures JSON/coverage/test artifacts, invokes Trivy once with relevant scanners, then writes normalized quality/security reports.
```


- [ ] **Step 5: Run tooling tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_tooling -v`

Expected: PASS.

- [ ] **Step 6: Commit minimal tooling policy**

Run: `git add src/nexus_harness/tooling.py tests/test_tooling.py core/policies/tooling.toml && git commit -m "feat: enforce minimal quality toolchain"`.

---

### Task 5: Build affected Docker images once and emit immutable deploy manifest

**Files:**
- Create: `src/nexus_harness/build.py`
- Create: `src/nexus_harness/deploy_manifest.py`
- Create: `tests/test_build.py`
- Create: `core/ci/deploy-manifest.schema.json`

**Interfaces:**
- Consumes: Affected image plan and Git SHA.
- Produces: Image build plan, GHCR digest capture and deploy manifest that contains no mutable production tag.

- [ ] **Step 1: Write failing immutable-manifest test**

Create `tests/test_build.py`:

```python
import unittest
from nexus_harness.deploy_manifest import DeployManifest

class BuildTests(unittest.TestCase):
    def test_manifest_rejects_latest_tag(self):
        with self.assertRaises(ValueError):
            DeployManifest(service="web", image="ghcr.io/acme/web:latest", digest="")
```

- [ ] **Step 2: Run build test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_build -v`

Expected: import failure.

- [ ] **Step 3: Implement build plan**

For each affected image, generate a deterministic BuildKit command with cache-from/cache-to scoped by image name. Tag with Git SHA for human discoverability, push once, then resolve and record the registry digest.

Implementation contract:

```text
Implement build plan
For each affected image, generate a deterministic BuildKit command with cache-from/cache-to scoped by image name. Tag with Git SHA for human discoverability, push once, then resolve and record the registry digest.
```


- [ ] **Step 4: Implement immutable deploy manifest**

Manifest format:

```json
{
  "repository": "Rubens-Marques/SDR-Plataform",
  "commit": "9e6f3ccc19dee64c03e771c87a01679d4ab9a98e",
  "artifacts": [{
    "service": "web",
    "image": "ghcr.io/rubens-marques/sdr-plataform-web",
    "digest": "sha256:..."
  }]
}
```

Reject empty digest and `latest` as production identity.

- [ ] **Step 5: Run build/manifest tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_build -v`

Expected: PASS.

- [ ] **Step 6: Commit immutable build pipeline**

Run: `git add src/nexus_harness/build.py src/nexus_harness/deploy_manifest.py tests/test_build.py core/ci/deploy-manifest.schema.json && git commit -m "feat: build immutable deployment artifacts"`.

---

### Task 6: Create restricted client-VM deploy contract

**Files:**
- Create: `infra/client-vm/nexus-deploy`
- Create: `infra/client-vm/install-deploy-user.sh`
- Create: `infra/client-vm/README.md`
- Create: `tests/test_deploy_contract.py`

**Interfaces:**
- Consumes: Approved deploy manifest and per-client profile.
- Produces: Restricted deployment command with explicit service/digest, health check and rollback.

- [ ] **Step 1: Write failing deploy-input test**

Create `tests/test_deploy_contract.py` that invokes the deploy parser with:
- a valid `service=web` + `sha256:` digest and expects acceptance;
- `latest` and expects rejection;
- an unknown service and expects rejection;
- a command containing shell metacharacters and expects rejection.

Implementation contract:

```text
Write failing deploy-input test
Create `tests/test_deploy_contract.py` that invokes the deploy parser with: - a valid `service=web` + `sha256:` digest and expects acceptance; - `latest` and expects rejection; - an unknown service and expects rejection; - a command containing shell metacharacters and expects rejection.
```


- [ ] **Step 2: Run deploy contract test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_deploy_contract -v`

Expected: missing parser/command.

- [ ] **Step 3: Implement allowlisted deploy parser**

`nexus-deploy` accepts only action `deploy`, an allowlisted service name from `/etc/nexus-deploy/services.json`, and a `sha256:` digest. It updates a local environment/compose variable, pulls by digest, recreates only the named service, checks configured health URL, and restores the previous digest on failure.

Implementation contract:

```text
Implement allowlisted deploy parser
`nexus-deploy` accepts only action `deploy`, an allowlisted service name from `/etc/nexus-deploy/services.json`, and a `sha256:` digest. It updates a local environment/compose variable, pulls by digest, recreates only the named service, checks configured health URL, and restores the previous digest on failure.
```


- [ ] **Step 4: Create deploy-user installer**

Create user `nexus-deploy` with no standing application shell workflow. Install root-owned deploy script and restrict the CI public key to the deploy command. Keep client-specific hostnames/keys outside the harness repository in the selected project profile/secrets store.

Implementation contract:

```text
Create deploy-user installer
Create user `nexus-deploy` with no standing application shell workflow. Install root-owned deploy script and restrict the CI public key to the deploy command. Keep client-specific hostnames/keys outside the harness repository in the selected project profile/secrets store.
```


- [ ] **Step 5: Run deploy contract tests**

Run: `python3 -m unittest tests.test_deploy_contract -v`

Expected: PASS.

- [ ] **Step 6: Commit client deploy contract**

Run: `git add infra/client-vm tests/test_deploy_contract.py && git commit -m "feat: restrict client vm deployments"`.

---

### Task 7: Implement infra doctor and CI budget report

**Files:**
- Create: `src/nexus_harness/infra.py`
- Create: `tests/test_infra.py`
- Create: `docs/operations/ci-budget.md`

**Interfaces:**
- Consumes: CI VPS state, project CI history when available, and configured budget.
- Produces: Human-readable security/health posture plus estimated GitHub-hosted/self-hosted cost.

- [ ] **Step 1: Write failing infra-status test**

Create `tests/test_infra.py`:

```python
import unittest
from nexus_harness.infra import summarize_health

class InfraTests(unittest.TestCase):
    def test_failed_disk_threshold_blocks_ci_host(self):
        report = summarize_health({"disk_percent": 96, "runner": True, "docker": True})
        self.assertEqual(report.gate, "FAIL")
```

- [ ] **Step 2: Run infra test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_infra -v`

Expected: import failure.

- [ ] **Step 3: Implement CI-host health summary**

Check disk, memory, runner status, container engine, cache directory writability and clock. Default hard fail at 95% disk; warn at 85%. No external monitoring service is added.

Implementation contract:

```text
Implement CI-host health summary
Check disk, memory, runner status, container engine, cache directory writability and clock. Default hard fail at 95% disk; warn at 85%. No external monitoring service is added.
```


- [ ] **Step 4: Implement CI budget output**

Report graph-estimated self-hosted CPU minutes and GitHub-hosted minutes. Default policy target is `github_hosted_minutes = 0` for ordinary private-repository PRs.

Implementation contract:

```text
Implement CI budget output
Report graph-estimated self-hosted CPU minutes and GitHub-hosted minutes. Default policy target is `github_hosted_minutes = 0` for ordinary private-repository PRs.
```


- [ ] **Step 5: Run infra tests and full Plan 4 suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v && scripts/validate`.

Expected: PASS.

- [ ] **Step 6: Commit Plan 4 completion**

Run: `git add src/nexus_harness/infra.py tests/test_infra.py docs/operations/ci-budget.md && git commit -m "feat: report ci host health and budget"`.

---
