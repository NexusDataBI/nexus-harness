# Client VM — restricted deploy contract

Provisioning files for an **isolated client production VM** that accepts
immutable image digests through a single restricted SSH command. The Canonical
Harness repository never stores client hostnames, IPs, SSH private keys, or
registry credentials.

## What this is (and is not)

- **Is:** a force-command deploy identity (`nexus-deploy`) that can only run
  `deploy <allowlisted-service> <sha256:digest>`, pull/recreate that one
  Compose service, health-check, and roll back the previous digest on failure.
- **Is not:** an interactive shell, a general `docker compose` front-end, or a
  place to push `latest` / mutable tags.

## Layout (on the client VM after install)

| Path                                              | Purpose                                  |
| ------------------------------------------------- | ---------------------------------------- |
| `/usr/local/bin/nexus-deploy`                     | Root-owned restricted entrypoint         |
| `/usr/local/lib/nexus-deploy/deploy_contract.py`  | Parser + deploy/rollback logic           |
| `/etc/nexus-deploy/services.json`                 | Allowlisted services (operator-supplied) |
| `/var/lib/nexus-deploy/`                          | Rollback evidence                        |
| `nexus-deploy` (system user, `/usr/sbin/nologin`) | SSH identity; no standing app shell      |

## Allowlist (`services.json`)

Operator-maintained on the client (from the project profile / secrets store):

```json
{
  "services": {
    "web": {
      "compose_file": "/opt/app/docker-compose.yml",
      "project_dir": "/opt/app",
      "env_file": "/opt/app/.env",
      "digest_var": "WEB_IMAGE_DIGEST",
      "image": "ghcr.io/example/app-web",
      "health_url": "http://127.0.0.1:8080/health"
    }
  }
}
```

Only service names matching `^[a-z0-9][a-z0-9-]*$` are accepted. Digests must
match `^sha256:[0-9a-f]{64}$`. Unknown services, `latest`, shell metacharacters,
arbitrary paths, and arbitrary Compose targets are rejected.

## Install

On the **client VM** as root (supply the CI public key at install time — do not
commit it):

```bash
export NEXUS_DEPLOY_PUBKEY='ssh-ed25519 AAAA... ci-nexus-deploy'
# Optional: path to this client's allowlist
# export NEXUS_DEPLOY_SERVICES_SRC=/path/to/services.json
sudo -E ./install-deploy-user.sh
```

The installer:

1. Creates system user `nexus-deploy` with shell `/usr/sbin/nologin`.
2. Installs the root-owned deploy script + helper.
3. Writes `~nexus-deploy/.ssh/authorized_keys` with
   `command="/usr/local/bin/nexus-deploy"` and forwarding disabled.

## Deploy flow

With `authorized_keys command=/usr/local/bin/nexus-deploy`, OpenSSH ignores a
client-supplied remote binary and always runs the forced command. The three
tokens must appear in `SSH_ORIGINAL_COMMAND` (or as direct argv when invoking
the binary locally):

```bash
# From CI — remote command becomes SSH_ORIGINAL_COMMAND:
ssh -i ci_deploy_key nexus-deploy@CLIENT_HOST 'deploy web sha256:<64 hex>'

# Local / forced-command already attached:
/usr/local/bin/nexus-deploy deploy web sha256:<64 hex>
```

The entrypoint splits `SSH_ORIGINAL_COMMAND` on whitespace only (no shell
evaluation) and validates each token.

1. Capture previous digest from the service `env_file` / `digest_var`.
2. Write the new digest; `docker compose pull` + `up -d --force-recreate --no-deps` **only** for that allowlisted service.
3. HTTP health check against `health_url`.
4. **PASS** only if health succeeds. Compose exit 0 alone is not enough.
5. On health failure: restore previous digest, recreate the same service, health again, write rollback evidence under `/var/lib/nexus-deploy/`.

## Security notes

- Parse argv in Python; never `eval` user strings in a shell.
- No standing production shell workflow for the deploy user.
- Keep client-specific data in the selected project profile / secrets store —
  out of this repository.
