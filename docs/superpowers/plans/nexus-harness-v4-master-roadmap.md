# Nexus Harness v4 — Master Implementation Roadmap

**Goal:** Migrate the exported v3 harness into a canonical, low-cost, graph-governed v4 without modifying the original archive.

## Execution dependency graph

```text
P1 Canonical Core & Migration
      │
      ▼
P2 Workflow/Graph/Quality/Security
      │
      ▼
P2.5 Nexus Memory
      │
      ▼
P3 Runtime Adapters & Hooks
      │
      ▼
P4 CI/VPS/Docker
      │
┌─────┼──────────┐
▼     ▼          ▼
P5    P6         P7
Project Frontend PostHog
Gov    Visual QA Incidents
└─────┼──────────┘
      ▼
P8 Release/Evals/Doctor
```

Dependency: `Plan 2 → Plan 2.5 → Plan 3`. Plans 3–8 keep their original numbers.

## Plans

1. `docs/superpowers/plans/2026-08-25-nexus-harness-v4-01-canonical-core-migration.md`
2. `docs/superpowers/plans/2026-08-25-nexus-harness-v4-02-workflow-graph-quality.md`
   2.5. `docs/superpowers/plans/2026-08-25-nexus-harness-v4-25-memory.md`
3. `docs/superpowers/plans/2026-08-25-nexus-harness-v4-03-runtime-adapters-hooks.md`
4. `docs/superpowers/plans/2026-08-25-nexus-harness-v4-04-ci-vps-security-docker.md`
5. `docs/superpowers/plans/2026-08-25-nexus-harness-v4-05-github-project-governance.md`
6. `docs/superpowers/plans/2026-08-25-nexus-harness-v4-06-frontend-visual-qa.md`
7. `docs/superpowers/plans/2026-08-25-nexus-harness-v4-07-posthog-incident-intelligence.md`
8. `docs/superpowers/plans/2026-08-25-nexus-harness-v4-08-release-evals-doctor.md`

## Milestone exits

| Milestone | Required outcome                                                                                           |
| --------- | ---------------------------------------------------------------------------------------------------------- |
| M1        | Canonical source exists; duplicate scanner and compiler skeleton pass tests                                |
| M2        | A task can move 0→8 with structured state, DAG, evidence, quality/security reports and completion blocking |
| M3        | Claude/Cursor/Codex outputs are generated from canonical source and drift is detected                      |
| M4        | Self-hosted VPS can execute affected CI, build immutable images and produce deploy manifests               |
| M5        | Mutable work can create/link Issues and PRs and synchronize lifecycle status                               |
| M6        | Material frontend change produces Playwright/browser/screenshot evidence and motion review                 |
| M7        | PostHog signals can be normalized/deduplicated into actionable GitHub Issues                               |
| M8        | Full migration, doctor, golden tests and private evals pass; v4 release archive is reproducible            |

## Cutover policy

The v3 installation remains usable until M8. No phase deletes the original archive or overwrites installed runtime configuration without an explicit install command. v4 installs are atomic and retain the previous generated dist for rollback.

## Implementation method

Use one fresh execution context per plan. Within a plan, use a fresh worker/reviewer per task where the runtime supports it. Every task ends with a test cycle and a commit when the implementation repository has Git metadata.
