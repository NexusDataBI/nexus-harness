# Harness behavioral evals

Harness evals are the executable specification of **Nexus governance behavior**.

They answer: given a classified task and state, did the Harness make the correct routing/gating decision?

They do not replace application tests.

## When an eval is required

Create/update an eval when a change affects:

- classification or scope routing;
- issue/tracking hierarchy;
- affected-component/check selection;
- quality-profile selection;
- approvals or remote-mutation permission;
- security/visual requirements;
- completion or merge readiness;
- shipping/deploy permission;
- memory/incident governance;
- any invariant whose regression would change agent behavior.

A reproduced Harness failure becomes a permanent regression case.

## When not to create one

Ordinary product code belongs to TDD/project tests and `nexus-verify`.

Examples that normally **do not** need a Harness eval:

- fixing a calculation bug in an application;
- adding an API endpoint;
- changing a React component inside established Harness policy;
- refactoring product code without changing Nexus routing/gates.

Add a Harness eval only if the case is specifically testing how Nexus should govern that work.

## Lifecycle

```text
expected behavior defined
→ case added
→ current Harness run (baseline / RED)
→ implementation
→ affected case GREEN
→ full deterministic eval suite
→ review
```

Do not rewrite expectations after seeing the candidate just to make it pass.

## Case contract

Use `evals/cases/*.json` and the existing deterministic runner.

```json
{
  "name": "example",
  "classification": {
    "intent": "change",
    "scope": "bounded",
    "domains": ["frontend"],
    "risk": "medium",
    "environment": "local",
    "quality_profile": "strict",
    "work_type": "feature",
    "mutable": true
  },
  "input": {
    "authorize_remote_mutation": false,
    "state": {
      "issue": 1,
      "acceptance": [{"id": "AC-1", "status": "FAIL"}]
    }
  },
  "expect": {
    "classification": {},
    "tracking": {},
    "graph": {},
    "quality_profile": {},
    "approvals": {},
    "security": {},
    "completion": {},
    "ship": {},
    "forbidden": ["remote_mutation", "live_model", "paid_inference"]
  }
}
```

Keep expectations minimal: assert the behavior that defines the regression, not unrelated implementation details.

## Invariants

These failures are blockers rather than score deductions:

1. no remote mutation from deterministic evals;
2. no live/paid model required for release PASS;
3. no implementation gate bypass when required tracking/acceptance is missing;
4. no acceptance promotion from stale or conversational evidence;
5. no required approval bypass;
6. implementation completion is not shipping permission;
7. material visual evidence must be current for the relevant diff;
8. production deploy identity must remain immutable when policy requires it.

## Evaluation style

Prefer deterministic policy functions and exact/structural assertions. Do not add LLM-as-a-judge where code can decide the result.

Report individual failures; do not hide a critical invariant behind an aggregate score.

## Regression discipline

When a production or development incident reveals wrong Harness behavior:

1. reduce it to the smallest reproducible task/state;
2. add the eval case and confirm current failure;
3. identify the owning policy/router;
4. change one meaningful behavior;
5. rerun the case and full suite;
6. keep the case permanently.
