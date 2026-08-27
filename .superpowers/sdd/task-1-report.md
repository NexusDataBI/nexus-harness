# Task 1 Report — PostHog configuration / privacy boundary

## Status

DONE

## Implemented

- `core/observability/posthog.toml` — safe defaults: `enabled=false`, `runtime_automation_enabled=false`, `free_tier_preferred=true`, conservative privacy/replay, never-capture field list. No secrets.
- `src/nexus_harness/posthog.py` — sole PostHog HTTP/config boundary:
  - `PostHogConfig` + `safe_dict()` redaction
  - secret only from `POSTHOG_PERSONAL_API_KEY` env or injected arg (toml secret keys ignored)
  - https-only host validation (reject file/javascript/localhost/credentials/path/query tricks)
  - configurable host/region (no single hardcoded DEFAULT_HOST)
  - injectable urllib transport, timeout, bounded response size, explicit JSON
  - `list_problems()` / `get_quota()` → provider `UNKNOWN` on auth/rate-limit/network/invalid/server failures (never empty list / never zero quota)
- `tests/test_posthog_config.py` — network-free coverage of the above
- `core/ci/profile.schema.json` — optional `[observability]` with `provider` / `id` / `host` only (no token fields)
- `harness.lock` refreshed via `write_lock` after engine/core changes

Did **not** configure `profiles/projects/sdr-platform.toml` with PostHog ids. Did **not** start Tasks 2–7. No real PostHog, no push, no GitHub Issues.

## TDD evidence

### RED

Command:

```text
PYTHONPATH=src python3 -m unittest tests.test_posthog_config -v
```

Observed:

```text
ImportError: Failed to import test module: test_posthog_config
ModuleNotFoundError: No module named 'nexus_harness.posthog'
FAILED (errors=1)
```

### GREEN

Command:

```text
PYTHONPATH=src python3 -m unittest tests.test_posthog_config -v
```

Observed:

```text
Ran 13 tests in 0.003s
OK
```

Related (schema / PROJECT.md token exclusion / CI profile):

```text
PYTHONPATH=src python3 -m unittest tests.test_posthog_config tests.test_project_doc tests.test_devserver.DevServerProfileTests -v
Ran 27 tests in 0.006s
OK
```

Lock refresh:

```text
PYTHONPATH=src python3 -c "from pathlib import Path; from nexus_harness.lockfile import write_lock; write_lock(Path('.'))"
```

## Files changed

| Path | Action |
| --- | --- |
| `tests/test_posthog_config.py` | created |
| `src/nexus_harness/posthog.py` | created |
| `core/observability/posthog.toml` | created |
| `core/ci/profile.schema.json` | updated (optional observability) |
| `harness.lock` | updated |

## Self-review

- Secrets never written to toml, schema, sdr-platform profile, or `safe_dict()` values.
- Exception/log paths redact `phx_`/`phc_` keys and Authorization assignments.
- Provider failure returns `problems=None` with `status=UNKNOWN` — not `[]`.
- Quota failure returns `QuotaAvailability.UNKNOWN` with `used`/`limit` as `None` — not `0`.
- Stdlib urllib only; transport injectable for network-free tests.
- Scope limited to Task 1.

## Concerns

None material. `load_ci_profile` still does not parse `[observability]` into `CiProfile` (schema allows it; `config_from_profile` / PROJECT.md consume the mapping). Enough for Task 1; wiring into `CiProfile` can wait until a later task needs it.
