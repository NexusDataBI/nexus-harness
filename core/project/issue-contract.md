# Issue contract

Every mutable correction, improvement or feature has a GitHub Issue before implementation. The Issue is the canonical work record. Read-only inspection, research and explanation do not create Issues unless explicitly requested.

## Required fields

- Summary
- Type
- Priority
- Project/Area
- Problem or desired outcome
- Acceptance Criteria
- Risk/Environment
- Evidence links when bug/incident
- Dependencies

## Bug additions

For a confirmed bug also record:

- Reproduction
- Proximate Cause
- Root Cause
- Escape Cause
- Regression Guard
- Preventive Control

High/blocker bugs require a regression guard or an explicit documented reason why one is impossible.

Non-bug work uses the required fields only. Do not invent empty Reproduction, Proximate Cause, Root Cause, Escape Cause, Regression Guard or Preventive Control sections to satisfy ceremony.

## Hierarchy

Use one Issue for a bounded bug by default. Use Project → Epic → Feature / Story / Bug → Task only when independent deliverables exist. Never create an empty child Issue solely to satisfy hierarchy.
