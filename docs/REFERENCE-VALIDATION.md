# External Reference Validation — 2026-08-25

The implementation design was checked against current official documentation before planning.

## GitHub

- Self-hosted runners can execute GitHub Actions jobs on infrastructure the user already maintains; the runner machine itself is user-managed.
- GitHub recommends ephemeral self-hosted runners for autoscaling/cleaner job isolation. The v4 baseline starts simpler with a dedicated private-repository runner and preserves an upgrade path to ephemeral/JIT execution.
- GitHub Projects supports custom fields, automation, views and roadmaps.
- GitHub Issues supports nested sub-issues, enabling Epic/Feature/Task hierarchy without Jira.
- Reusable workflow configuration is available, but the Harness compiler remains the canonical source because managed repositories span different owners/accounts and the same compiler must also target non-GitHub runtime adapters.

## Minimal toolchain

The final baseline deliberately has one primary tool per responsibility:
- Biome — JS/TS lint + format.
- Vitest — JS/TS unit/integration + coverage.
- Playwright — browser/E2E/screenshots/visual evidence.
- Trivy — security scanning across source/dependencies/secrets/config/images/SBOM.
- PostHog Cloud — product analytics/session replay/runtime problem intelligence.

No additional SaaS is required by the baseline.
