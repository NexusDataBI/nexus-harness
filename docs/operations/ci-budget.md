# CI budget — GitHub-hosted vs self-hosted

## Policy (default)

Ordinary **private-repository** PRs target:

```text
github_hosted_minutes = 0
```

Configured in `core/graph/scheduler.toml`:

```toml
[order]
github_hosted_only_by_exception = true

[billing]
target_github_hosted_minutes_per_normal_pr = 0
```

Scheduler order: local → self-hosted Nexus CI VPS → GitHub-hosted **only by exception**.

A graph node does **not** imply a billed GitHub Actions job. Prefer batching cheap nodes on the self-hosted runner.

## Report

`nexus_harness.infra.estimate_ci_budget` produces a `CiBudgetReport` with:

| Field                          | Meaning                                                                                 |
| ------------------------------ | --------------------------------------------------------------------------------------- |
| `self_hosted_cpu_minutes`      | Graph-estimated CPU minutes on `execution_target=self_hosted` (sum of `estimated_cost`) |
| `github_hosted_minutes`        | Graph-estimated minutes on `execution_target=github_hosted`                             |
| `target_github_hosted_minutes` | Policy target (default `0` for normal private PRs)                                      |
| `within_policy`                | `github_hosted_minutes <= target`                                                       |

Optional CI history can supply observed minutes when a graph is unavailable. No Datadog / Grafana / Sentry — budget is local graph + history only.

## Health doctor

`summarize_health(facts)` gates the CI host from an injectable facts dict (shell doctor or tests). Disk defaults: hard fail at **≥95%**, warn at **≥85%**. Also covers memory, runner, container engine, cache writability, clock skew, required directories, and tool availability when provided.
