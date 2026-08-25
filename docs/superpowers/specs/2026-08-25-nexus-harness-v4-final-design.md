# Nexus Harness v4 — Final Consolidated Design

**Status:** Approved architecture, consolidated for implementation  
**Date:** 2026-08-25  
**Supersedes:** `nexus-harness-v4-design.md`, `nexus-harness-v4-design-quality-gates.md`, `nexus-harness-v4-design-quality-gates-ratchet.md`, `nexus-harness-v4-design-graph-ci.md`

## 1. Goal

Build a single canonical engineering harness that governs Claude Code, Cursor and Codex without duplicating skills, prompts, policies or project-specific configuration. The harness must make agentic software development predictable, auditable, low-cost and safe while preserving high autonomy for local development.

The system has five permanent responsibilities:

1. **Workflow governance** — every mutable engineering task follows the Nexus lifecycle.
2. **Task graph orchestration** — independent work can run in parallel; dependencies, conflicts, invalidation and cost are explicit.
3. **Quality and security gates** — output is a candidate until deterministic evidence and fresh review prove it acceptable.
4. **Project governance** — GitHub Issues, Projects and PRs are the operational system of record.
5. **Low-cost execution** — local execution first, self-hosted CI second, GitHub-hosted compute only as an exception.

## 2. Non-negotiable principles

1. One canonical implementation per skill.
2. Runtime artifacts are generated outputs, never canonical sources.
3. Core policies use roles/capabilities, not model names.
4. The 0→9 lifecycle is mandatory governance for mutable work.
5. Lifecycle stages can compile to a DAG; governance order does not imply serial execution.
6. Every stage has an explicit state: `PENDING`, `PASS`, `FAIL`, `SKIP`, `BLOCKED`, `WAITING_APPROVAL`.
7. Acceptance criteria begin `FAIL`; only recorded evidence promotes them to `PASS`.
8. Conversation history is not operational state. Task state, Git, Issues, PRs and evidence are authoritative.
9. Hooks enforce deterministic rules; skills teach judgment and process.
10. Production access is never a global implicit permission.
11. Shipping is separate from implementation.
12. Every code-changing correction, improvement or feature has a GitHub Issue before implementation.
13. Every PR references its Issue.
14. Quality is ratcheted: a PR may maintain or improve governed metrics but may not silently weaken them.
15. A model output is a candidate, not final code.
16. One primary tool per responsibility; prefer free/open-source/local execution.
17. Adding a new external service requires an uncovered capability and explicit approval.
18. GitHub is the system of record for work; PostHog is the system of record for product/runtime behavior.
19. Production deploys use immutable artifacts/digests; deployment state must not require a follow-up source-code PR.
20. Human attention is reserved for judgment, architecture, risk acceptance and production gates—not routine lint/test babysitting.

## 3. Final minimal tool stack

| Responsibility | Primary tool | Cost policy |
|---|---|---|
| Work tracking, Issues, Projects, PRs, Actions, registry | GitHub | Existing account |
| Product analytics, session replay, error/runtime intelligence | PostHog Cloud | Free tier first; hard spend limit |
| Format/lint/static style quality for JS/TS | Biome | Free/open source |
| Unit + integration + coverage for JS/TS | Vitest | Free/open source |
| E2E + browser + screenshots + visual regression | Playwright | Free/open source |
| Security scan for source/deps/secrets/IaC/images/SBOM | Trivy | Free/open source |
| CI compute | Personal Nexus VPS | Already paid |
| Production runtime | Per-client VM | Isolated from CI |

The harness does not add Jira, Linear, Trello, Slack, Sentry, Datadog, New Relic, Grafana, Codecov, Semgrep, Gitleaks, Knip, Stryker or ArchContract to the baseline. A project may retain an existing tool when removal would reduce quality, but the harness does not introduce overlapping tools by default.

Non-JS repositories map the same responsibilities to their existing native commands instead of forcing the JS toolchain.

## 4. Canonical repository shape

```text
nexus-harness/
├── core/
│   ├── constitution.md
│   ├── policies/
│   │   ├── approvals.toml
│   │   ├── autonomy.toml
│   │   ├── filesystem.toml
│   │   ├── git.toml
│   │   ├── network.toml
│   │   ├── production.toml
│   │   ├── project-tracking.toml
│   │   └── tooling.toml
│   ├── workflow/
│   │   ├── lifecycle.toml
│   │   ├── classification.toml
│   │   ├── completion.toml
│   │   ├── task-state.schema.json
│   │   └── acceptance.schema.json
│   ├── graph/
│   │   ├── graph.schema.json
│   │   ├── scheduler.toml
│   │   ├── impact.toml
│   │   └── locks.toml
│   ├── quality/
│   │   ├── quality-report.schema.json
│   │   ├── ratchet.toml
│   │   ├── profiles.toml
│   │   └── evidence.toml
│   ├── security/
│   │   ├── security-report.schema.json
│   │   ├── policy.toml
│   │   └── infrastructure.toml
│   └── project/
│       ├── registry.schema.json
│       ├── issue-contract.md
│       ├── pr-contract.md
│       └── project-fields.toml
├── src/
│   └── nexus_harness/
│       ├── cli.py
│       ├── config.py
│       ├── state.py
│       ├── workflow.py
│       ├── graph.py
│       ├── quality.py
│       ├── security.py
│       ├── project.py
│       ├── github.py
│       ├── evidence.py
│       ├── adapters.py
│       └── install.py
├── skills/
│   ├── nexus-workflow/
│   ├── nexus-quality/
│   ├── nexus-verify/
│   ├── nexus-handoff/
│   ├── nexus-ship/
│   ├── nexus-frontend/
│   └── accessibility/
├── agents/
│   ├── explorer.md
│   ├── planner.md
│   ├── implementer.md
│   ├── reviewer.md
│   ├── verifier.md
│   ├── pr-reviewer.md
│   ├── bug-triage.md
│   ├── root-cause-analyst.md
│   ├── test-reviewer.md
│   ├── security-reviewer.md
│   ├── database-reviewer.md
│   ├── performance-reviewer.md
│   ├── frontend-visual-reviewer.md
│   ├── accessibility-reviewer.md
│   └── information-quality-reviewer.md
├── upstream/
│   ├── superpowers/
│   ├── matt-pocock/
│   ├── impeccable/
│   └── vendor-lock.json
├── profiles/
│   ├── default.toml
│   ├── frontend.toml
│   ├── backend.toml
│   ├── database.toml
│   ├── infra.toml
│   ├── production-readonly.toml
│   └── projects/
├── hooks/
│   ├── session-init
│   ├── prompt-router
│   ├── policy-gate
│   ├── failure-memory
│   ├── batch-maintenance
│   ├── completion-gate
│   ├── checkpoint-state
│   ├── compact-observer
│   ├── config-drift
│   └── session-end
├── adapters/
│   ├── claude/
│   ├── cursor/
│   └── codex/
├── ci/
│   ├── workflow.template.yml
│   ├── affected.py
│   ├── quality_gate.py
│   ├── build_plan.py
│   └── deploy_manifest.py
├── infra/
│   ├── ci-vps/
│   └── client-vm/
├── scripts/
│   ├── nexus
│   ├── build
│   ├── validate
│   ├── install
│   ├── diff
│   ├── audit
│   └── doctor
├── tests/
├── evals/
├── docs/
├── harness.lock
└── README.md
```

Machine-readable canonical configuration uses TOML/JSON so the runtime can use Python 3.11+ standard-library parsing without a YAML dependency. Human policy and contracts remain Markdown.

## 5. Authority hierarchy

1. Explicit user task instruction.
2. Safety/security hard policy.
3. Repository/environment profile.
4. Nexus Workflow and deterministic policies.
5. Nexus domain skill.
6. Upstream primitive.
7. Runtime default.

An upstream skill may help execute a stage but may not create a competing lifecycle.

## 6. Mandatory lifecycle

```text
USER TASK
   ↓
0 CLASSIFY
   ↓
1 ACCEPTANCE
   ↓
2 EXPLORE
   ↓
3 DESIGN / PLAN
   ↓
4 WORKTREE / ISOLATION
   ↓
5 IMPLEMENT
   ↓
6 VERIFY + QUALITY + SECURITY
   ↓
7 FRESH REVIEW
   ↓
8 DONE GATE
   ↓
9 SHIP
```

Read-only work may skip mutation stages with a recorded reason.

### 6.1 Stage 0 — CLASSIFY

Record:

```text
intent: inspect | change | debug | design | review | migrate | ship
scope: trivial | bounded | architectural | long_horizon
domains: frontend | backend | database | security | infra | docs | tooling
risk: low | medium | high | critical
environment: local | staging | production
quality_profile: light | standard | strict | critical
```

Also resolve whether this is a new task or continuation, repository identity, project identity, required approvals, issue-tracking requirement and likely graph nodes.

### 6.2 Tracking gate

For `change`, `debug`, `migrate` and implementation-bearing `design` work, a GitHub Issue must exist before Stage 5. The Issue is the canonical work record.

Read-only inspection, research and explanation do not create Issues unless explicitly requested.

### 6.3 Stage 1 — ACCEPTANCE

Every acceptance criterion starts `FAIL`.

```json
{
  "id": "AC-001",
  "statement": "Invalid refresh token returns 401",
  "status": "FAIL",
  "verification": {
    "kind": "integration_test",
    "command": "npm run test --workspace apps/server"
  },
  "evidence": null
}
```

A criterion can become `PASS` only when the evidence ledger contains current evidence for the same diff hash.

### 6.4 Stage 2 — EXPLORE

Default explorer is fresh, read-only and progressively scoped. It reads task state, repository instructions, Git state, relevant architecture/tests/files, external docs when needed, and history only when it clarifies intent.

### 6.5 Stage 3 — DESIGN / PLAN

- trivial: internal micro-plan;
- bounded: short plan;
- architectural/long horizon: written design + explicit approval + implementation plan.

Approval is mandatory for architecture/public API, broad restructure, production, authentication/schema production changes, destructive actions, significant scope changes, material external cost/risk and major dependency upgrades.

### 6.6 Stage 4 — ISOLATION

Significant mutations use a Git worktree. Preserve unrelated user changes. Record base commit and worktree path. In a non-Git environment, record a justified `SKIP`.

### 6.7 Stage 5 — IMPLEMENT

Loop:

```text
RED / reproduce
→ minimal change
→ GREEN
→ justified refactor
→ checkpoint
```

Obscure bugs require root-cause diagnosis before patching. Repeated identical failures trigger failure memory instead of blind retry.

### 6.8 Stage 6 — VERIFY + QUALITY + SECURITY

Deterministic checks run before LLM judgment. The affected graph determines which checks are necessary.

For the default JS/TS profile:

```text
Biome
Vitest unit/integration/coverage
Playwright when browser behavior is affected
Trivy source/config/image as appropriate
project build/typecheck when configured
Quality Ratchet
```

### 6.9 Stage 7 — FRESH REVIEW

Reviewer context consists of spec/Issue/acceptance criteria, diff and evidence—not the implementer's full chain of thought. Specialist reviewers are activated by domain/risk. `blocker` and `high` confirmed findings block completion.

### 6.10 Stage 8 — DONE GATE

Require:

- Issue linked when tracking is required;
- acceptance criteria `PASS`;
- evidence fresh for current diff;
- Verify/Quality/Security `PASS`;
- Review `PASS` or justified `SKIP`;
- zero confirmed blocker/high findings;
- verified/reviewed diff hash equals current diff;
- required approvals recorded;
- no implicit shipping.

Result is `READY_TO_SHIP` or `DONE_NOT_SHIPPED`.

### 6.11 Stage 9 — SHIP

Only when requested or explicitly approved:

```text
prepare → commit → push → PR → CI → PR babysitting
→ fresh review → merge → build immutable artifact
→ deploy → health/smoke → close Issue
```

Production deploy is an explicit gate.

## 7. Graph Engineering

The lifecycle governs state; the graph governs execution.

### Node

Each graph node records:

```text
id
stage
kind
dependencies
reads
writes
affected_paths
risk
execution_target
estimated_cost
status
evidence_outputs
```

### Edge types

- `depends_on`
- `invalidates`
- `conflicts_with`
- `requires_gate`
- `produces_for`
- `promotes`

### Weights

- token cost;
- wall time;
- CPU time;
- GitHub-hosted minutes;
- risk;
- blast radius;
- confidence.

### Scheduler order

```text
local
→ self-hosted Nexus VPS
→ GitHub-hosted only by exception
```

Graph node does not imply GitHub Actions job. Cheap nodes should be batched to avoid per-job billing overhead.

### Resource conflicts

Two workers that write the same file/resource cannot run concurrently unless the graph explicitly defines a merge strategy. Shared schema/config migrations serialize by default.

## 8. Quality Gate and Ratchet

Quality gates have three rule types:

1. `absolute` — must satisfy a fixed condition.
2. `ratchet` — may maintain or improve baseline but never regress.
3. `budget` — tolerance-based for noisy metrics.

Default examples:

```text
build/type errors      absolute
failing tests          absolute
critical security      absolute
coverage               ratchet
lint warnings          ratchet
duplication            ratchet when measured
performance            budget when enabled
```

The baseline lives in `.nexus/quality/baseline.json` in each project. A PR that materially improves a ratcheted metric updates the baseline in the same PR. The gate rejects weakening the baseline and rejects a stale baseline when an improvement is supposed to become the new floor.

Agents may never weaken policy, baseline, acceptance criteria or waiver rules to make their own changes pass.

## 9. Evidence ledger

Operational state:

```text
~/.nexus-harness/state/<repo-id>/<task-id>/
├── state.json
├── evidence.jsonl
├── quality-report.json
├── security-report.json
├── failures.json
├── tool-summary.jsonl
└── handoff.md
```

Every evidence item stores command, exit code, timestamp, base commit, diff hash, artifact path and limitation. Any relevant code change invalidates stale evidence.

## 10. Bug intelligence

A finding has:

```text
status: suspected | confirmed | rejected
severity: blocker | high | medium | low | info
confidence: high | medium | low
origin: introduced_by_change | pre_existing | unknown
```

A suspected bug is not promoted to confirmed without reproduction/evidence.

Confirmed bugs use a Bug Card with:

```text
symptom
reproduction
proximate cause
root cause
escape cause
systemic cause when present
regression guard
preventive control
```

High/blocker bugs require a regression guard or an explicit documented reason why one is impossible.

## 11. PR intelligence and babysitting

PR flow:

```text
intake
→ risk classification
→ diff cartography
→ deterministic checks
→ specialist review
→ bug verification
→ root cause
→ dedupe/triage
→ fix
→ verify again
→ fresh review
```

CI failures are consumed from structured outputs before raw logs. The agent may loop while measurable progress is occurring. Repeated failure fingerprints with no material change force root-cause analysis; persistent failure becomes `BLOCKED`.

## 12. GitHub Project Governance

GitHub is the work system of record.

Initial central Project:

```text
Owner: Rubens-Marques
Name: Nexus Engineering
```

Recommended fields:

- Project
- Type
- Status
- Priority
- Area
- Client
- Iteration
- Risk
- Environment
- Quality
- Security
- Target date

Hierarchy:

```text
Project
→ Epic
→ Feature / Story / Bug
→ Task
```

Use hierarchy only when it reduces ambiguity. A bounded bug may be a single Issue.

Statuses:

```text
Inbox
Planned
Ready
In Progress
Review
Blocked
Verifying
Done
```

The harness updates status from lifecycle events. Project boards do not maintain a separate manual truth.

Every repository has a short `PROJECT.md` containing identity, GitHub link, current focus, runtime profile, quality profile, observability identifier and canonical commands.

## 13. Minimal external-tool policy

```text
one_primary_tool_per_responsibility = true
prefer_existing = true
prefer_free = true
prefer_open_source = true
prefer_local_execution = true
```

A new external service requires:

1. an uncovered capability;
2. material benefit;
3. evidence existing tools cannot reasonably cover it;
4. explicit approval.

## 14. Frontend quality

`nexus-frontend` is the single frontend entry skill. It routes to focused upstream references such as Impeccable, Motion Principles, Vercel React guidance, design system and accessibility.

Material visual changes require vision-in-the-loop:

```text
start/reuse localhost
→ baseline screenshot when relevant
→ implement
→ Playwright interaction
→ desktop/mobile screenshots
→ console/network review
→ visual reviewer
→ fix
→ screenshot again
```

Visual evidence becomes stale after relevant UI changes.

Motion policy:

- animate only when motion improves comprehension;
- use skeletons only when content shape is predictable and wait is meaningful;
- lazy-load non-critical resources;
- use progress indicators when progress/wait is meaningful;
- respect `prefers-reduced-motion`;
- avoid unnecessary hover scaling, stagger and decorative animation;
- review loading, empty, error and transition states.

## 15. CI architecture

### Control plane

Personal Nexus VPS runs CI/quality/security compute.

### Production plane

Each client VM runs only its production workload. CI and production credentials are separated.

### CI execution

```text
local agent checks
→ PR
→ required self-hosted Nexus Quality Gate
→ merge
→ build affected immutable artifact once
→ push to GHCR
→ deploy approved digest
→ smoke
```

Target GitHub-hosted minutes per normal PR: `0`.

Use `concurrency` with cancel-in-progress to stop obsolete PR runs.

Do not repeat the full validation on `main` when the protected branch guarantees the exact merged candidate already passed required gates. Post-merge jobs should build/promote/deploy only what is necessary.

### Self-hosted runner

Baseline deployment uses a dedicated `nexus-ci` Unix account and private repositories only. CI jobs have no standing production secrets. Rootless container tooling is preferred. The design leaves an upgrade path to ephemeral/JIT runners as scale increases.

### Build strategy

```text
build once
→ immutable digest
→ promote same digest
```

No production `latest` dependency. No deploy-only PR whose purpose is to record the image already running.

## 16. Security baseline

Single primary scanner: Trivy.

Security graph covers:

- source/dependency vulnerabilities;
- secrets;
- Dockerfile/IaC misconfiguration;
- image vulnerability scan;
- SBOM.

Container policy:

```text
root user forbidden unless justified
privileged forbidden
secrets in image forbidden
mutable production tag forbidden
healthcheck required
resource limits required
critical vulnerability blocks
high vulnerability with available fix blocks by default
```

VM baseline:

- SSH keys only;
- root SSH disabled;
- password SSH disabled;
- firewall default-deny;
- production database not publicly exposed;
- security updates;
- backup freshness;
- restore drill status;
- disk/CPU/RAM/health checks;
- per-client credentials.

The harness provides `nexus infra doctor` to report posture without adding a monitoring SaaS.

## 17. PostHog and incident intelligence

PostHog Cloud is the only baseline product/runtime analytics SaaS.

Use it for product analytics, session replay, error tracking and the runtime signals available in the selected PostHog plan. Set a hard spend limit and remain inside free tier while possible.

Runtime problem flow:

```text
PostHog signal
→ fingerprint/dedupe
→ severity policy
→ actionable?
→ GitHub Issue
→ implementation/PR
→ release SHA/digest
→ post-deploy verification
```

Do not create one GitHub Issue per raw event. Aggregate first.

A runtime-derived Issue links available PostHog session/error identifiers, release SHA, environment and reproduction evidence.

## 18. Skill hierarchy and consolidation

### Canonical Nexus skills

- `nexus-workflow`
- `nexus-quality`
- `nexus-verify`
- `nexus-handoff`
- `nexus-ship`
- `nexus-frontend`
- `accessibility`

### Superpowers

Use as engineering primitives, not as a competing global spine:

- brainstorming
- writing-plans
- test-driven-development
- systematic-debugging
- using-git-worktrees
- verification-before-completion
- requesting-code-review
- receiving-code-review
- finishing-a-development-branch

### Matt Pocock

Optional discovery/research/ticketing primitives. Remove the mandatory seven-phase global workflow.

### Frontend specialists retained

Keep canonical or upstream sources for:

- Impeccable
- design-motion-principles
- fixing-motion-performance
- visual-validation
- vercel-react-best-practices
- vercel-composition-patterns
- feature-sliced-design
- ui-craft-dense-dashboard
- design-system
- brand
- extract-design-system
- variant
- banner-design when creative assets are relevant

Merge overlapping frontend entrypoints into `nexus-frontend` modes.

### Safe deletion rule

Never delete an overlapping skill by name alone.

1. compare full content;
2. extract unique heuristics/examples/references;
3. classify as canonical skill, policy, reference or discard;
4. run golden/skill tests;
5. remove old entrypoint.

Byte-identical duplicates may be removed after canonical copy exists.

## 19. Runtime adapters

### Claude

Generate minimal `CLAUDE.md`, settings and hooks. Use prompt routing, completion gate, failure memory, compact checkpoint/restore and policy gate. Do not embed project-specific production IPs or commands globally.

### Cursor

Generate minimal user/project rules and enable sandbox. No global production deploy policy. No global model mandate.

### Codex

Generate minimal `AGENTS.md` and config. Remove Claude-specific environment variables and project-specific filesystem/trust settings from global configuration.

## 20. Compiler/install model

```text
canonical source
→ validate
→ resolve upstream lock
→ render adapters
→ static/security checks
→ generate dist
→ diff installed
→ atomic install
→ doctor/smoke
```

`harness.lock` stores schema version, upstream revisions, canonical hashes, adapter versions and generated hashes. Generated runtime artifacts are immutable outputs; manual edits are drift.

## 21. Initial migration facts

The exported v3 package contains 2,397 files according to its manifest and includes duplicated skills/configuration across `agents-skills`, Claude, Cursor and Codex. The previous sync subsystem is blocked by its own circuit breaker.

Migration must:

- remove AppleDouble `._*`;
- remove `.bak`, stale caches and orphaned generated copies;
- deduplicate byte-identical content;
- merge divergent overlapping skills only after semantic comparison;
- remove project/client-specific IPs, SSH targets and paths from global config;
- remove hardcoded model routing from the constitution;
- fix compaction around structured task state;
- replace bidirectional sync with one-way compile/install;
- produce before/after file, duplicate and byte counts.

The original archive remains immutable.

## 22. Success criteria

The v4 migration is complete when:

1. one canonical source exists per skill;
2. no byte-identical runtime skill copies are manually maintained;
3. system prompts trigger Nexus Workflow;
4. mutable tasks cannot implement without tracked acceptance criteria and required Issue;
5. completion gate blocks false-done;
6. repeated unchanged failures trigger diagnosis;
7. compaction preserves structured state;
8. Cursor sandbox is enabled;
9. no production target is global;
10. no model names appear in core constitution;
11. upstream revisions are locked;
12. `dist` is reproducible;
13. quality/security reports are structured and ratcheted;
14. frontend material changes produce browser evidence;
15. CI can run on the personal VPS with near-zero GitHub-hosted compute;
16. affected builds prevent unnecessary server/web/worker rebuilds;
17. deployment uses immutable artifacts and no deploy-only PR;
18. GitHub Issues/PRs/Project status remain synchronized with lifecycle;
19. PostHog runtime problems can be triaged into deduplicated Issues;
20. `nexus doctor` and smoke/eval suites pass for Claude, Cursor and Codex.
