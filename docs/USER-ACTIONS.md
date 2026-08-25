# USER ACTIONS — Nexus Harness v4

Este arquivo contém somente ações que dependem de uma decisão, credencial ou infraestrutura do usuário. Não coloque tokens, senhas ou chaves privadas neste arquivo.

## Before implementation

- [ ] Create or choose a private Git repository for the canonical harness. Recommended name: `NexusDataBI/nexus-harness`; if organization access is not ready, use a temporary private repository and migrate later.
- [ ] Ensure the implementation repository includes Git metadata before execution so worktrees/commits/reviews can be used.
- [ ] Keep `/mnt/data/nexus-harness-export-20260825-094238.tar.gz` read-only as the migration source.

## GitHub access

- [ ] Grant the GitHub integration/CLI access needed for `NexusDataBI/marketing-hub` and other NexusDataBI repositories.
- [ ] Authenticate `gh` on the development machine and on the personal CI VPS with the minimum permissions required for Issues, PRs, Actions/Packages and Projects.
- [ ] Create the central GitHub Project named `Nexus Engineering`. Initial owner may be `Rubens-Marques`; move it to the organization later only if that reduces friction.
- [ ] Protect `main`/default branches before removing duplicate post-merge full validation: require the Nexus Quality Gate and block direct pushes where feasible.

## Personal Nexus CI VPS

- [ ] Confirm Ubuntu/Linux VPS SSH access with sudo.
- [ ] Confirm available CPU, RAM and free disk before installing the self-hosted runner.
- [ ] Create a backup/snapshot before changing Docker/runner configuration.
- [ ] Do not paste the VPS private SSH key into prompts or repository files.
- [ ] Supply GitHub runner registration credentials only during the install command; store long-lived credentials in the appropriate secret store.

## Client production VMs

For each client:

- [ ] Confirm which repository/services deploy to that VM.
- [ ] Confirm a production health endpoint/command.
- [ ] Create a dedicated restricted deployment identity/key.
- [ ] Keep client VM IP/hostname, SSH key and production secrets in the project-local secret/profile layer, not the global harness.
- [ ] Snapshot/backup production before the first Nexus-controlled deployment cutover.

## PostHog Cloud

- [ ] Create or select one PostHog project per product where separation is useful.
- [ ] Enable a hard billing/spend limit and keep the account on free-tier usage while possible.
- [ ] Store PostHog personal API credentials only in environment/GitHub secrets.
- [ ] Review privacy/session-replay masking before enabling recordings in production.
- [ ] Define the product identifiers used by `projects.toml`.

## Project bootstrap

For each managed repository:

- [ ] Decide whether existing lint/test tools will be migrated now or retained temporarily. The harness must not install overlapping tools blindly.
- [ ] Add `.nexus/quality/baseline.json` only after the first measured baseline run.
- [ ] Review generated `PROJECT.md`, CI profile and deployment profile before the first automated PR/deploy.
- [ ] For repositories outside the connected GitHub installation, grant access before expecting automatic Issue/PR/Project synchronization.

## Cutover approval

- [ ] Review `docs/release/v4-acceptance.md` after implementation.
- [ ] Explicitly approve installation into real Claude/Cursor/Codex user configuration.
- [ ] Explicitly approve the first production deploy per client profile.
