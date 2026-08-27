# PostHog instrumentation checklist

Use this checklist when wiring a Nexus project to PostHog Cloud. Goal: product
events, errors, and session replay share one release identity — without a second
observability SaaS and without capturing secrets or unrestricted PII.

## Checklist

### 1. Product events for meaningful user actions

- [ ] Instrument product events only for meaningful user actions (not every click).
- [ ] Attach `release_context(...)` metadata (`project`, `environment`, `release`,
      `deployment_digest`, optional `route` / `session` / `tenant`) to each event.
- [ ] Prefer pseudonymous user / tenant / client ids — never email, phone, or name
      unless explicitly authorized (default: no).

### 2. Error tracking init

- [ ] Initialize PostHog error tracking once at app boot (client and/or server).
- [ ] Inject the same release identity used for product events.
- [ ] Confirm errors land under the correct project and environment.

### 3. Session replay with conservative privacy masking

- [ ] Enable session replay only when needed; default is off / conservative.
- [ ] Mask all sensitive inputs. Never capture passwords, tokens, Authorization,
      cookies, payment fields, secrets, client credentials, or raw API keys.
- [ ] Align field denylist with harness `NEVER_CAPTURE_FIELDS` (password, token,
      authorization, cookie(s), payment, secret, client_credentials, api_key, …).

### 4. Release identity injection

- [ ] Set `release` to the Git commit SHA of the deployed revision.
- [ ] Set `deployment_digest` from Plan 4 `DeployManifest.digest` (`sha256:<64 hex>`).
      This is the production identity — do **not** invent a second digest.
- [ ] If digest is unavailable, record `null` / `UNKNOWN` explicitly. Never invent one.
- [ ] Use `nexus_harness.observability.release_context` (or equivalent) so keys stay
      consistent across events, errors, and replay.

### 5. Environments distinguishable from production

- [ ] Tag every payload with `environment`: exactly one of `production`, `staging`,
      or `development`.
- [ ] Verify development and staging traffic is distinguishable from production in
      PostHog filters / dashboards (no shared ambiguous labels like `prod` / `dev`).

### 6. Pseudonymous identity preference

- [ ] Prefer pseudonymous user / tenant / client identifiers.
- [ ] Do not send emails, phones, or names by default.
- [ ] Never put secrets, tokens, Authorization headers, or cookies in release context.

## Quick verification

```python
from nexus_harness.observability import release_context

ctx = release_context("abc123", "production", "sdr-platform", digest=manifest.digest)
assert ctx["release"] == "abc123"
assert ctx["environment"] == "production"
assert ctx["project"] == "sdr-platform"
assert ctx["deployment_digest"].startswith("sha256:")
```

When digest is missing:

```python
ctx = release_context("abc123", "staging", "sdr-platform")
assert ctx["deployment_digest"] in (None, "UNKNOWN")
```
