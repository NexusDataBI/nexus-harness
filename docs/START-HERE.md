# START HERE — Nexus Harness v4

## What this bundle is

This is the approved architecture and implementation package for rebuilding the existing Nexus harness into v4. It does not modify the original export and does not yet install anything into Claude, Cursor, Codex, GitHub, the CI VPS or client production VMs.

## Read in this order

1. `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`
2. `docs/MASTER-ROADMAP.md`
3. `USER-ACTIONS.md`
4. `MIGRATION-MAP.md`
5. The implementation plan corresponding to the current milestone.

## Implementation order

1. Canonical Core & Migration
2. Workflow, Graph, Quality & Security
3. Runtime Adapters & Hooks
4. CI VPS, Security & Docker
5. GitHub Project Governance
6. Frontend Visual QA
7. PostHog Incident Intelligence
8. Release, Evals & Doctor

Plans 1–3 can be developed after Plan 1. **Plan 4 must not start until the Plans 1–3 Repair Gate reports `READY_FOR_PLAN_4`.** Plans 5–7 should start only after the shared lifecycle/CI contracts they consume are stable.

## Target everyday experience after v4

The developer primarily sees two external interfaces:

- **GitHub** — Projects, Issues, PRs, CI/CD, registry and delivery history.
- **PostHog** — product behavior, session replay and runtime problem evidence.

Biome, Vitest, Playwright and Trivy run as automated CLI tools under local/Nexus VPS orchestration instead of becoming four additional dashboards to maintain.

## Cost target

- GitHub-hosted compute for ordinary private PRs: approximately zero.
- CI compute: personal Nexus VPS.
- Quality/security tools: free/open source.
- PostHog: free tier first with spend cap.
- No baseline Jira/Linear/Trello/Slack/Sentry/Datadog/New Relic/Grafana/Codecov dependency.

## Execution method

Use the implementation plans as the work source. Do not skip their verification gates. For each plan, prefer fresh workers per task and a fresh reviewer before accepting the task.
