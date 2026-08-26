# Pull request contract

Every PR references its Issue. Draft PRs may exist before all checks are green.

## Required fields

- Summary
- Linked Issue
- Scope
- Acceptance status
- Verification
- Quality/Security summary
- Screenshots for frontend when required
- Deployment impact
- Known limitations

The PR body renders those fields as Summary, Issue, Scope, Acceptance, Verification, Quality, Security, Deployment impact and Known limitations. Quality/Security summary is the Quality and Security sections together. Frontend evidence (screenshots included) appears only when the change is frontend.

## Issue reference

- Use `Closes #N` only when the PR fully resolves the Issue.
- Otherwise use `Refs #N`.

## Merge readiness

Merge readiness is the existing completion Done Gate (`evaluate_completion`). `READY_TO_SHIP` is the merge-ready condition; surface it as `READY_TO_MERGE`. Do not invent a second independent Done Gate.

Block ready/merge when any of the following is true:

- Issue missing when tracking is required
- acceptance incomplete
- fresh evidence missing
- quality or security gate failed
- review gate failed
- confirmed blocker or high finding exists
- required evidence is stale
- reviewed or verified diff is stale

Draft PRs may exist before all checks are green. Draft is not merge-ready.
