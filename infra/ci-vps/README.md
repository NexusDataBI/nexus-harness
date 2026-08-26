# Nexus CI VPS — dedicated self-hosted runner host

Provisioning files for a personal Ubuntu VPS that runs the Nexus Quality Gate
as a **persistent** GitHub Actions self-hosted runner under the `nexus-ci`
system user.

## What this is (and is not)

A persistent self-hosted runner is **not equivalent** to an ephemeral clean VM
(or a fresh GitHub-hosted `ubuntu-latest` job). The same host, user, disk, and
caches survive across jobs. Treat isolation as a hard operational concern, not
something the runner binary gives you for free.

### Isolation limitations (read before enabling)

1. **Workspace cleanup between jobs** — the runner work directory under
   `/var/lib/nexus-ci/cache/_work` may retain files, credentials from checkout,
   and tool caches. Prefer explicit cleanup steps in workflows; do not assume
   a pristine filesystem per job.
2. **No standing production credentials** — do not place production SSH keys,
   DB passwords, deploy tokens, or client secrets on this host as long-lived
   files. Inject short-lived secrets per job (or not at all) when needed.
3. **Prefer ephemeral job containers when viable** — run build/test steps inside
   containers that discard state on exit. Host-level tooling is for the runner
   agent and bounded caches only.
4. **Avoid unrestricted Docker socket when possible** — mounting
   `/var/run/docker.sock` into jobs grants host-level control. Prefer rootless
   Docker for `nexus-ci` and job-scoped containers. The installer warns when
   only the system socket is available.
5. **Shared disk & network** — one compromised job can read sibling workspaces,
   caches under `/var/lib/nexus-ci`, and reach the same egress IP. Private
   repositories only; no multi-tenant untrusted workloads on this host.
6. **Upgrade path** — as scale or trust boundary needs grow, move toward
   ephemeral/JIT runners rather than thickening this persistent host.

## Layout

| Path                          | Purpose                               |
| ----------------------------- | ------------------------------------- |
| `/opt/nexus-runner`           | GitHub Actions runner binary + config |
| `/var/lib/nexus-ci/cache`     | Runner work + tool caches             |
| `/var/lib/nexus-ci/artifacts` | Bounded artifact staging              |
| `/var/lib/nexus-ci/logs`      | Host/runner logs                      |
| `nexus-ci` (system user)      | Runs the systemd unit (never root)    |

## Prerequisites

- Ubuntu with sudo/root
- Docker Engine installed; **rootless** for `nexus-ci` preferred
- Private-repository GitHub runner **registration token** (ephemeral; create
  from the repo/org settings at install time)
- Runner binary version chosen at install time (not pinned in this repo)

## Install

```bash
# On the CI host (example — supply your own version and token; never commit them)
export RUNNER_VERSION=2.321.0
export RUNNER_REPO_URL=https://github.com/ORG/PRIVATE_REPO
export RUNNER_TOKEN=...   # or pipe the token on stdin

sudo -E ./install.sh
# stdin alternative:
# printf '%s' "$RUNNER_TOKEN" | sudo RUNNER_VERSION=... RUNNER_REPO_URL=... ./install.sh
```

The installer is idempotent: re-running skips existing `nexus-ci` user creation,
reuses matching runner version under `/opt/nexus-runner`, and skips
`config.sh` when `.runner` is already present.

`RUNNER_VERSION` is **required**. Tokens are read from `RUNNER_TOKEN` /
`GITHUB_RUNNER_TOKEN` / `REGISTRATION_TOKEN` or stdin and are never echoed.

## systemd

Unit file: `nexus-ci.service` → installed as `/etc/systemd/system/nexus-ci.service`.

- `User=nexus-ci` / `Group=nexus-ci`
- `WorkingDirectory=/opt/nexus-runner`
- `ExecStart=/opt/nexus-runner/run.sh`

```bash
sudo systemctl status nexus-ci
sudo journalctl -u nexus-ci -f
```

## Health: `nexus ci-host doctor`

Interim shell wrapper (Python `summarize_health` is Task 7):

```bash
nexus-ci-host doctor
# or directly:
./nexus-ci-host-doctor.sh
```

Checks disk free space, memory availability, Docker/rootless socket, runner
directories and process, and outbound HTTPS to `api.github.com`.

## What this repo never contains

- Client IP addresses
- GitHub PATs / registration tokens
- SSH private keys or production secrets
- Analytics/observability SaaS agents (Sentry, Datadog, New Relic, Grafana
  Agent, etc.)

## Labels

Register with labels `self-hosted,nexus-ci` so workflows using
`runs-on: [self-hosted, nexus-ci]` land on this host.
