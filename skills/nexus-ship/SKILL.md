---
name: nexus-ship
description: "Commit, push, PR, merge, and deploy gates. Shipping is separate from implementation. Use only when shipping is requested or explicitly approved."
---

# nexus-ship

Owns **commit / push / PR / merge / deploy gates**. Implementation reaching Done is not permission to ship.

## Gate

Ship only when requested or explicitly approved. Production deploy is a further explicit gate. Echo **repo + branch + tenant/system + command** and confirm before any remote mutation.

## Local before remote

Validate with `nexus-verify` (and the profile from `nexus-quality`) on the current diff. If the local gate fails, do not push. CI is not a paid debugger.

## Commit

- Only when requested or approved.
- Conventional Commits; atomic; no secrets.
- Feature branch `tipo/nome-kebab` unless the repo documents otherwise.
- No force-push on shared branches.
- Every code-changing PR references a GitHub Issue when tracking is required.

## Push and CI

- Push the feature branch; do not use CI as the first typecheck.
- Never configure `on.push.branches: ["**"]`. CI runs on `pull_request` and `push` to the default branch.
- Docs/skills/markdown-only changes should not wake heavy CI when the repo supports `paths-ignore`.
- Prefer concurrency cancel-in-progress on the same PR.

## PR

1. Open **draft** while WIP or while heavy jobs must stay off.
2. Title + Summary + Test plan; base = default branch.
3. Keep the open-PR count small (~2–3 per repo). Close or merge zombies first.
4. Mark **ready** only when the slice is intended to merge soon (quality already green).
5. Draft = cheap quality. Ready = full required jobs (integration/security as the repo defines).

## Merge

Merge only with required checks green, or with an explicit human acceptance of risk when cloud CI is unavailable. Prefer squash when the branch is WIP-noisy. Delete the remote branch when the repo does not auto-delete.

## Deploy

- Immutable artifacts identified by digest. No mutable `:latest` as the release identity. Do not deploy "source PR" as the artifact.
- Build once, promote the same digest.
- Read the repo deploy profile (historically `.claude/deploy-profile.md`). If missing, stop and ask for a profile — do not invent hosts.
- Forensic/log work approved in-session runs **before** recreate/up.
- CI credentials stay off the production plane.

## Unique glue preserved from nexus-ship / deploy

Draft→ready CI budget, no `branches: ["**"]`, confirm-before-deploy, deploy-profile required, billing-exhausted CI is an ops problem not a code fix. Project-specific VPS IPs, client auto-deploy, and Marketing Hub workflow names are **not** canonical.

## Anti-patterns

- Shipping because implementation finished
- Ready PR "to see if CI passes" on every agent commit
- Mass re-runs when the shared Actions budget is exhausted
- Deploy without echoing target and waiting for confirmation
