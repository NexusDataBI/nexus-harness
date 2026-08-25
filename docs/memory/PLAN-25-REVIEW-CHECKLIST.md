# Plan 2.5 Memory — Review Checklist

Use this checklist when the agent returns the Plan 2.5 report and repository/ZIP.

## Architecture

- [ ] Project durable memory and Plan 2 operational memory are separate.
- [ ] Portfolio vault is optional and not required for project recall.
- [ ] Markdown+JSON are canonical.
- [ ] SQLite/FTS is derived and rebuildable.
- [ ] No embeddings/vector DB/SaaS introduced.
- [ ] Obsidian is optional UI only.
- [ ] No Claude-Mem dependency introduced.

## Authority

- [ ] Explicit current spec/instruction outranks memory.
- [ ] Current repo/fresh evidence outranks memory.
- [ ] Candidate memory cannot act as truth.
- [ ] Stale memory cannot silently enter normal capsule.
- [ ] Contradictions are surfaced rather than silently overwritten.

## Lifecycle

- [ ] New memories start CANDIDATE.
- [ ] VERIFIED requires provenance.
- [ ] Type-specific promotion rules exist.
- [ ] SUPERSEDED/REJECTED/ARCHIVED are excluded from recall.
- [ ] Stale memory can be reverified.

## Security

- [ ] Secret-like content is rejected before write.
- [ ] Secret values are not echoed in errors/logs.
- [ ] No raw `.env`, token, private key or bearer credential accepted.
- [ ] No absolute user path committed to canonical core.
- [ ] Confidential memory is not automatically injected.

## Storage

- [ ] Markdown/JSON pairs are atomic.
- [ ] Duplicate IDs are rejected.
- [ ] Doctor catches orphan pairs.
- [ ] Derived caches can be deleted.
- [ ] Project memory folders contain no runtime-specific database truth.

## Retrieval

- [ ] Deterministic scoring is implemented.
- [ ] FTS5 is optional.
- [ ] Lexical fallback is tested.
- [ ] Relevant path/tag memories rank above unrelated memories.
- [ ] Stable ordering is tested.
- [ ] Candidate/stale exclusion is tested.

## Context capsules

- [ ] HOT/WARM limits are deterministic.
- [ ] Max item count is enforced.
- [ ] Provenance remains visible for included items.
- [ ] Stale warnings are separate from injected context.
- [ ] No raw transcript is rendered.

## Plan 2 safety

- [ ] Acceptance semantics unchanged.
- [ ] Evidence semantics unchanged.
- [ ] Completion Gate cannot be bypassed through memory.
- [ ] Quality/Security gates unchanged.
- [ ] Failure memory remains operational, not durable by default.

## Plan 3 readiness

- [ ] `session_recall` exists.
- [ ] candidate checkpoint/restore exists.
- [ ] `consolidate_memory` exists.
- [ ] runtime-neutral public exports exist.
- [ ] Plan 3 integration document exists.
- [ ] Master roadmap shows Plan 2 → Plan 2.5 → Plan 3.

## Verification

- [ ] Memory suites freshly PASS.
- [ ] Full unittest suite freshly PASS.
- [ ] `scripts/validate` freshly exits 0.
- [ ] Final reviewer has 0 open BLOCKER/HIGH.
- [ ] No push/PR/VPS/PostHog/deploy occurred.
