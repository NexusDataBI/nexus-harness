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

## Issue reference

- Use `Closes #N` only when the PR fully resolves the Issue.
- Otherwise use `Refs #N`.

## Merge readiness

Block ready/merge when any of the following is true:

- Issue missing when tracking is required
- acceptance incomplete
- quality or security gate failed
- confirmed blocker or high finding exists
- required evidence is stale
