---
name: nexus-verify
description: "Deterministic evidence for Nexus Stage 6. Run checks, record the ledger, and refuse to promote acceptance from conversation history."
---

# nexus-verify

Owns **deterministic evidence**. Does not choose profiles (`nexus-quality`), does not serialize handoff (`nexus-handoff`), and does not ship (`nexus-ship`).

Conversation history is not evidence.

## Ledger item

Every evidence item records:

```text
command
exit_code
timestamp
base_commit
diff_hash
artifact_path
limitation
```

## Freshness

- Bound to the **current** diff hash.
- A relevant code (or UI) change invalidates prior evidence.
- An acceptance criterion becomes `PASS` only when `exit_code == 0` **and** the stored diff hash matches the current diff.

## Order

Deterministic checks run **before** LLM judgment. A failing phase stops the loop; fix, then resume from that phase. Pre-existing red suites are still a block, not a waiver.

Detect package manager and scripts from the repo. Do not assume `npm`.

Typical sequence (subset required by the quality profile and affected graph):

1. Build / image when Dockerfile or compose is in the diff
2. Typecheck when configured
3. Format / lint
4. Unit / integration tests (+ coverage when the profile requires it)
5. Security scan (Trivy for source/config/image as appropriate; secrets grep on the diff)
6. Dead code **introduced by this diff** only
7. Diff review: unintended files, swallowed errors, secrets, out-of-scope paths

Frontend visual evidence is owned by `nexus-frontend` visual-validate; this skill still records the commands and hashes.

## Report

```text
VERIFY — [branch] diff=[hash]
Build / Types / Lint / Tests / Security / Diff: PASS|FAIL|SKIP
Gate: PASS | FAIL
Limitations: …
```

`PASS` means the required profile checks ran against the current diff and the ledger is fresh. Then `nexus-quality` interprets ratchet and selects reviewers.

## Unique glue preserved from verification-loop

Fail-closed phases, lockfile-based command selection, secrets/debug grep on the **diff** (not the whole repo), and dead-code cleanup limited to this change. Project-specific `npm` recipes are not canonical; translate to the repo's scripts.
