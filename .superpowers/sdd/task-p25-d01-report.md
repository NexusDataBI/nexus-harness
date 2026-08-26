# P25-D01 Report

Status: resolved on `feat/v4-memory`.

TDD RED: targeted tests failed at import because `AuthorityContradiction` was not yet defined.
TDD GREEN: targeted memory suite passed, 38 tests.
Full discover: passed, 232 tests.

Implemented explicit caller-supplied `AuthorityContradiction`, wired through
`MemoryQueryContext` and `session_recall`, and applied `resolve_contradiction`
to exclude higher-authority memories from HOT/WARM. Contradiction warnings expose
only memory ID, authority, and optional pointer; memory bodies are not emitted.
Weaker authorities remain eligible, and absent contradictions preserve existing
HOT behavior. P25-D01 is marked resolved in `docs/migration/debt.json`.

Commit: `fix: exclude memories contradicted by current repo`
Concerns: no semantic/LLM contradiction detector was added; callers must provide
known contradiction claims explicitly.
