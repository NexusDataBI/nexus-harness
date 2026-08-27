# Nexus Harness v4 — Final migration report

Numbers below are derived from `docs/migration/v3-baseline.json`,
`docs/migration/cleanup-report.json`, `docs/migration/skill-ledger.json`,
`docs/migration/debt.json`, `docs/migration/unique-heuristics.md`,
`docs/MIGRATION-MAP.md`, `harness.lock`, and a scan of the canonical
v4 trees plus `dist/`. No counts were invented.

## Source archive

- Expected SHA-256: `cfa547d0b27b149ba0350783da965a550f754d484ac39b0b5e9e7a5951b7b1a0`
- Recorded SHA-256: `cfa547d0b27b149ba0350783da965a550f754d484ac39b0b5e9e7a5951b7b1a0`
- SHA source: computed
- Archive present: yes
- Archive path: `inputs/nexus-harness-export-20260825-094238.tar.gz`
- Archive unchanged: yes

## File inventory

| Snapshot | Files | Duplicate files | Redundant bytes | Total bytes |
| --- | ---: | ---: | ---: | ---: |
| v3 baseline | 2398 | 1296 | 24976986 | 38847022 |
| v3 cleanup (tempfile extract) | 2317 | 1217 | 24248424 | 38114819 |
| v4 canonical + dist | 590 | 1 | 926 | 5639545 |

v4 after-scope: `core, skills, profiles, src, tests, upstream, dist`.

Duplicate extras in the v4 scan are split into intentional generated
repetition (`dist/`, `tests/golden/`) versus manually maintained copies:

- generated duplicate count/bytes: 1 / 926
- maintained duplicate count/bytes: 0 / 0
- generated artifacts (lock generated_hashes + engine_hashes): 116
- materialized dist files (excluding .gitkeep): 0

## Canonical skills

- canonical skill count: 7
- `accessibility`
- `nexus-frontend`
- `nexus-handoff`
- `nexus-quality`
- `nexus-ship`
- `nexus-verify`
- `nexus-workflow`

## Removed global project-specific configuration

- Hardcoded model routing
- Project-specific client rules
- VPS IP/SSH commands
- Absolute project directories
- Acelera/client automatic deployment rules
- Claude environment variables inside Codex configuration
- Disabled Cursor sandbox
- Global allow-everything command policy
- Mandatory Matt seven-phase lifecycle
- Compaction that duplicates constitution instead of restoring structured task state
- Bidirectional/blocked harness-sync

## Divergent skill decisions

Unresolved divergent-skill decisions: 0

- `code-review`: merge → `skills/nexus-quality/SKILL.md` (Claude and Codex copies differ; merge unique review heuristics into fresh Stage 7 reviewer agents, do not delete either source.)
- `impeccable`: upstream → `upstream/impeccable/SKILL.md` (Cursor copy adds license metadata and runtime path variants versus the shared agents/claude/codex hash; keep all sources and lock the retained upstream Impeccable tree.)
- `implement`: upstream → `upstream/matt-pocock/implement/SKILL.md` (Claude copy is longer than Codex; retain both as Matt Pocock upstream primitives and extract unique guidance before dropping an entrypoint.)
- `napkin`: reference → `none` (Claude copy is localized; agents-skills and Codex share a hash. Keep all sources as a focused reference, not a competing canonical skill.)
- `root-cause-tracing`: merge → `agents/root-cause-analyst.md` (Claude copy is localized; agents-skills and Codex share a hash. Merge unique tracing heuristics into systematic-debugging plus root-cause-analyst; do not delete either source.)
- `tdd-workflow`: merge → `skills/nexus-workflow/SKILL.md` (Claude and Codex copies diverge; merge unique Nexus workflow glue into nexus-workflow invoking Superpowers TDD, without deleting sources.)
- `token-optimizer`: reference → `none` (Claude tree copy differs mainly in frontmatter quoting from the shared agents-skills/Codex hash. Keep all sources as a reference; not a canonical v4 skill.)
- `ui-ux-pro-max`: extract_then_remove_entrypoint → `skills/nexus-frontend/SKILL.md` (Three distinct hashes (Claude is substantially larger). Extract unique heuristics into nexus-frontend, then remove the broad entrypoint; do not delete any source in this task.)

## Skill ledger (every semantic decision)

- `ask-matt`: upstream / unique → `upstream/matt-pocock/ask-matt/SKILL.md`
- `aws-skills`: reference / unique → `none`
- `babysitting-prs`: obsolete / unique → `none`
- `banner-design`: reference / exact_duplicate → `none`
- `baseline-ui`: reference / exact_duplicate → `none`
- `batch-grill-me`: upstream / unique → `upstream/matt-pocock/batch-grill-me/SKILL.md`
- `better-accessibility`: merge / exact_duplicate → `skills/accessibility/SKILL.md`
- `better-colors`: reference / exact_duplicate → `none`
- `better-interface`: reference / exact_duplicate → `none`
- `better-layout`: reference / exact_duplicate → `none`
- `better-typography`: reference / exact_duplicate → `none`
- `better-ui`: reference / exact_duplicate → `none`
- `better-writing`: reference / exact_duplicate → `none`
- `brand`: reference / exact_duplicate → `none`
- `calibracao-score-engajamento`: obsolete / unique → `none`
- `changelog-generator`: reference / unique → `none`
- `code-review`: merge / divergent → `skills/nexus-quality/SKILL.md`
- `codebase-design`: upstream / unique → `upstream/matt-pocock/codebase-design/SKILL.md`
- `content-research-writer`: reference / unique → `none`
- `context-mode`: reference / unique → `none`
- `ctx-cloud-setup`: reference / unique → `none`
- `ctx-cloud-status`: reference / unique → `none`
- `ctx-doctor`: reference / unique → `none`
- `ctx-stats`: reference / unique → `none`
- `ctx-upgrade`: reference / unique → `none`
- `deploy`: merge / exact_duplicate → `skills/nexus-ship/SKILL.md`
- `design`: reference / exact_duplicate → `none`
- `design-motion-principles`: upstream / exact_duplicate → `upstream/design-motion-principles/SKILL.md`
- `design-system`: reference / exact_duplicate → `none`
- `design-taste-frontend`: merge / exact_duplicate → `skills/nexus-frontend/SKILL.md`
- `diagnosing-bugs`: merge / unique → `upstream/superpowers/systematic-debugging/SKILL.md`
- `domain-modeling`: upstream / unique → `upstream/matt-pocock/domain-modeling/SKILL.md`
- `explain-interface`: merge / exact_duplicate → `skills/nexus-frontend/SKILL.md`
- `extract-design-system`: reference / exact_duplicate → `none`
- `feature-sliced-design`: reference / exact_duplicate → `none`
- `fixing-accessibility`: merge / exact_duplicate → `skills/accessibility/SKILL.md`
- `fixing-motion-performance`: reference / exact_duplicate → `none`
- `frontend-redesign-orchestrator`: merge / exact_duplicate → `skills/nexus-frontend/SKILL.md`
- `graphify`: reference / exact_duplicate → `none`
- `grill-me`: upstream / exact_duplicate → `upstream/matt-pocock/grill-me/SKILL.md`
- `grill-with-docs`: upstream / exact_duplicate → `upstream/matt-pocock/grill-with-docs/SKILL.md`
- `grilling`: upstream / unique → `upstream/matt-pocock/grilling/SKILL.md`
- `handoff`: merge / unique → `skills/nexus-handoff/SKILL.md`
- `impeccable`: upstream / divergent → `upstream/impeccable/SKILL.md`
- `implement`: upstream / divergent → `upstream/matt-pocock/implement/SKILL.md`
- `improve-codebase-architecture`: upstream / unique → `upstream/matt-pocock/improve-codebase-architecture/SKILL.md`
- `interface-review`: merge / exact_duplicate → `skills/nexus-frontend/SKILL.md`
- `limpeza-diaria-segura-mac`: obsolete / unique → `none`
- `napkin`: reference / divergent → `none`
- `nexus-frontend`: canonicalize / exact_duplicate → `skills/nexus-frontend/SKILL.md`
- `nexus-ship`: canonicalize / exact_duplicate → `skills/nexus-ship/SKILL.md`
- `owasp-security`: reference / unique → `none`
- `prototype`: upstream / unique → `upstream/matt-pocock/prototype/SKILL.md`
- `research`: upstream / unique → `upstream/matt-pocock/research/SKILL.md`
- `resolving-merge-conflicts`: upstream / unique → `upstream/matt-pocock/resolving-merge-conflicts/SKILL.md`
- `root-cause-tracing`: merge / divergent → `agents/root-cause-analyst.md`
- `setup-matt-pocock-skills`: upstream / unique → `upstream/matt-pocock/setup-matt-pocock-skills/SKILL.md`
- `skills-pack`: reference / unique → `none`
- `slides`: reference / exact_duplicate → `none`
- `software-architecture`: reference / unique → `none`
- `source-command-branch`: merge / exact_duplicate → `skills/nexus-ship/SKILL.md`
- `source-command-commit`: merge / exact_duplicate → `skills/nexus-ship/SKILL.md`
- `source-command-plan`: merge / exact_duplicate → `skills/nexus-workflow/SKILL.md`
- `source-command-pr`: merge / exact_duplicate → `skills/nexus-ship/SKILL.md`
- `source-command-push`: merge / exact_duplicate → `skills/nexus-ship/SKILL.md`
- `source-command-review`: merge / exact_duplicate → `skills/nexus-quality/SKILL.md`
- `subagent-driven-development`: upstream / unique → `upstream/superpowers/subagent-driven-development/SKILL.md`
- `systematic-debugging`: upstream / unique → `upstream/superpowers/systematic-debugging/SKILL.md`
- `tdd`: merge / unique → `upstream/superpowers/test-driven-development/SKILL.md`
- `tdd-workflow`: merge / divergent → `skills/nexus-workflow/SKILL.md`
- `teach`: upstream / unique → `upstream/matt-pocock/teach/SKILL.md`
- `test-driven-development`: upstream / unique → `upstream/superpowers/test-driven-development/SKILL.md`
- `to-questionnaire`: upstream / unique → `upstream/matt-pocock/to-questionnaire/SKILL.md`
- `to-spec`: upstream / exact_duplicate → `upstream/matt-pocock/to-spec/SKILL.md`
- `to-tickets`: upstream / exact_duplicate → `upstream/matt-pocock/to-tickets/SKILL.md`
- `token-coach`: reference / unique → `none`
- `token-optimizer`: reference / divergent → `none`
- `trail-of-bits-security`: reference / unique → `none`
- `triage`: upstream / unique → `upstream/matt-pocock/triage/SKILL.md`
- `ui-craft-dense-dashboard`: reference / exact_duplicate → `none`
- `ui-styling`: extract_then_remove_entrypoint / exact_duplicate → `skills/nexus-frontend/SKILL.md`
- `ui-ux-pro-max`: extract_then_remove_entrypoint / divergent → `skills/nexus-frontend/SKILL.md`
- `variant`: reference / exact_duplicate → `none`
- `varlock`: reference / unique → `none`
- `vercel-composition-patterns`: upstream / exact_duplicate → `upstream/vercel-composition-patterns/SKILL.md`
- `vercel-react-best-practices`: upstream / exact_duplicate → `upstream/vercel-react-best-practices/SKILL.md`
- `vercel-react-view-transitions`: reference / exact_duplicate → `none`
- `verification-loop`: merge / exact_duplicate → `skills/nexus-verify/SKILL.md`
- `vibesec`: reference / unique → `none`
- `visual-validation`: reference / exact_duplicate → `none`
- `vuca-reengajamento-conversao`: obsolete / unique → `none`
- `vuca-shadow-guards-flip-review`: obsolete / unique → `none`
- `vuca-worktree-housekeeping`: obsolete / unique → `none`
- `wayfinder`: upstream / unique → `upstream/matt-pocock/wayfinder/SKILL.md`
- `web-design-guidelines`: reference / exact_duplicate → `none`
- `webapp-testing`: reference / unique → `none`
- `writing-great-skills`: upstream / unique → `upstream/matt-pocock/writing-great-skills/SKILL.md`

## Unique heuristics

- `better-accessibility` reference files (`semantics-and-aria.md`, `focus-and-keyboard.md`, `forms.md`, `hit-areas.md`, `motion-and-zoom.md`, `screen-readers.md`) (exact_duplicate): PRESERVED: copied to `skills/accessibility/references/`. Same a11y skill; no second a11y product. `agents/openai.yaml` not copied.
- `ui-styling` (exact_duplicate): ALREADY_COVERED: stack-honor / do-not-impose-shadcn policy in `skills/nexus-frontend` implement + `references/router.md`. Encyclopedia, CLI recipes, and scripts DISCARDED_WITH_REASON (generic shadcn/Tailwind docs; remain in the immutable export).
- `ui-ux-pro-max` (divergent (3 hashes)): PRESERVED: search/explore contract and "recommendations never outrank brand/Figma/brief" in `skills/nexus-frontend/references/router.md`. Catalogs, scripts, and the three divergent entrypoints DISCARDED_WITH_REASON (export only).
- `implement` Claude vs Codex (divergent): ALREADY_COVERED: Claude copy is canonical at `upstream/matt-pocock/implement` (Nexus no-auto-commit patch). Codex-only wording DISCARDED_WITH_REASON — adapters consume the same Matt skill; do not duplicate per runtime.
- `code-review` Claude vs Codex (divergent): ALREADY_COVERED: two-axis review and Fowler smell baseline live in `skills/nexus-quality`. Tracker-setup prose DISCARDED_WITH_REASON — Issue tracking is Plan 5; Superpowers `requesting-code-review` / `receiving-code-review` load from the host runtime. Do not copy entire legacy review skills.
- `tdd-workflow` (divergent): ALREADY_COVERED: runner detection, plan-as-data, and RED/GREEN evidence mapping live in `skills/nexus-workflow`. TDD loop vocabulary stays Superpowers `test-driven-development`.
- `root-cause-tracing` (divergent): ALREADY_COVERED: "root-cause before patch" and failure-memory glue live in `skills/nexus-workflow` Stage 5. DISCARDED_WITH_REASON: do not invent `agents/root-cause-analyst.md` or missing Superpowers files; `systematic-debugging` is the imported primitive.
- `napkin` (divergent): DISCARDED_WITH_REASON: operator local note / reference only, not a canonical v4 skill. Remains in the immutable export.

## Debt

- resolved: P1-D01, P1-D02, P1-D03, P1-D04, P1-D05, P2-D01, P2-D02, P2-D03, P2-D04, P2-D05, P2-D06, P2-D07, P25-D01, P25-D02, P25-D03, P25-D04, P3-D02, P3-R01, P3-R02, P5-D01, P6-D01, P6-D02, P7-D01
- accepted residual: none
- unresolved: none

## Security cleanup

- `src/nexus_harness/security.py`
- `src/nexus_harness/pretool.py`
- `src/nexus_harness/command.py`
- `core/security/policy.toml`
- `core/security/infrastructure.toml`
- `core/policies/production.toml`
- `core/policies/filesystem.toml`
- `core/policies/network.toml`

## Runtime adapters

- `src/nexus_harness/adapters.py`
- `src/nexus_harness/runtime_claude.py`
- `src/nexus_harness/runtime_cursor.py`
- `src/nexus_harness/runtime_codex.py`
- `src/nexus_harness/compile.py`

## Memory

- `src/nexus_harness/memory/capsule.py`
- `src/nexus_harness/memory/store.py`
- `src/nexus_harness/memory/session.py`
- `core/memory/retrieval-policy.toml`
- `core/memory/memory-policy.toml`
- `core/memory/memory-record.schema.json`

## CI

- `src/nexus_harness/ci.py`
- `src/nexus_harness/affected.py`
- `src/nexus_harness/build.py`
- `core/ci/profile.schema.json`
- `core/ci/deploy-manifest.schema.json`

## GitHub

- `src/nexus_harness/github.py`
- `src/nexus_harness/hierarchy.py`
- `src/nexus_harness/tracking.py`
- `src/nexus_harness/pull_request.py`
- `core/project/issue-contract.md`
- `core/project/pr-contract.md`

## Frontend

- `src/nexus_harness/visual.py`
- `src/nexus_harness/playwright.py`
- `src/nexus_harness/frontend_review.py`
- `skills/nexus-frontend/SKILL.md`
- `core/quality/frontend.toml`
- `core/quality/visual-evidence.schema.json`

## PostHog

- `src/nexus_harness/posthog.py`
- `src/nexus_harness/incidents.py`
- `src/nexus_harness/incident_policy.py`
- `core/observability/posthog.toml`
- `core/observability/incidents.toml`
