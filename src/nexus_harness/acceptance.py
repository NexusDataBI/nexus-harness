"""Machine-checked mapping from final-spec §22 success criteria to evidence.

Live VPS / GitHub Project / PostHog never become PASS from local fixtures.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ALLOWED_STATES = frozenset({"PASS", "FAIL", "ACTIVATION_REQUIRED", "NOT_APPLICABLE"})
EVIDENCE_KINDS = frozenset(
    {
        "unit_test",
        "golden_test",
        "eval_case",
        "migration_report_field",
        "generated_config",
        "doctor_check",
        "validator",
        "release_manifest",
        "security_scan",
    }
)
LIVE_ONLY_IDS = frozenset({15, 18, 19})

SPEC_STATEMENTS = (
    "one canonical source exists per skill",
    "no byte-identical runtime skill copies are manually maintained",
    "system prompts trigger Nexus Workflow",
    "mutable tasks cannot implement without tracked acceptance criteria and required Issue",
    "completion gate blocks false-done",
    "repeated unchanged failures trigger diagnosis",
    "compaction preserves structured state",
    "Cursor sandbox is enabled",
    "no production target is global",
    "no model names appear in core constitution",
    "upstream revisions are locked",
    "dist is reproducible",
    "quality/security reports are structured and ratcheted",
    "frontend material changes produce browser evidence",
    "CI can run on the personal VPS with near-zero GitHub-hosted compute",
    "affected builds prevent unnecessary server/web/worker rebuilds",
    "deployment uses immutable artifacts and no deploy-only PR",
    "GitHub Issues/PRs/Project status remain synchronized with lifecycle",
    "PostHog runtime problems can be triaged into deduplicated Issues",
    "nexus doctor and smoke/eval suites pass for Claude, Cursor and Codex",
)


@dataclass(frozen=True)
class Evidence:
    kind: str
    path: str
    selector: str = ""
    note: str = ""


@dataclass(frozen=True)
class Criterion:
    id: int
    statement: str
    expected_status: str
    live: bool
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class CriterionResult:
    id: int
    statement: str
    status: str
    expected_status: str
    live: bool
    evidence: tuple[Evidence, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class MatrixReport:
    gate: str
    results: tuple[CriterionResult, ...]
    fail_count: int
    summary: str


def _ev(kind: str, path: str, selector: str = "", note: str = "") -> Evidence:
    return Evidence(kind=kind, path=path, selector=selector, note=note)


SUCCESS_CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        1,
        SPEC_STATEMENTS[0],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_skill_contracts.py",
                "test_canonical_skills_exist_once",
            ),
            _ev(
                "migration_report_field",
                "docs/migration/final-report.md",
                "canonical skill count: 7",
            ),
        ),
    ),
    Criterion(
        2,
        SPEC_STATEMENTS[1],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_migration_report.py",
                "test_repo_report_matches_frozen_baseline_and_zero_unresolved",
            ),
            _ev(
                "migration_report_field",
                "docs/migration/final-report.md",
                "maintained duplicate count/bytes: 0 / 0",
            ),
        ),
    ),
    Criterion(
        3,
        SPEC_STATEMENTS[2],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_runtime_claude.py",
                "test_constitution_is_minimal_and_points_to_canonical_memory",
            ),
            _ev(
                "unit_test",
                "tests/test_runtime_codex.py",
                "test_codex_output_is_minimal_and_canonical",
            ),
            _ev("golden_test", "tests/golden/claude/CLAUDE.md"),
            _ev("golden_test", "tests/golden/AGENTS.md"),
            _ev(
                "generated_config",
                "tests/golden/.cursor/rules/nexus-workflow.mdc",
            ),
        ),
    ),
    Criterion(
        4,
        SPEC_STATEMENTS[3],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_workflow.py",
                "test_cannot_enter_implement_without_acceptance",
            ),
            _ev(
                "unit_test",
                "tests/test_workflow.py",
                "test_tracking_requires_positive_issue_before_implement",
            ),
            _ev("eval_case", "evals/cases/ambiguous-task.json", "ambiguous-task"),
        ),
    ),
    Criterion(
        5,
        SPEC_STATEMENTS[4],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_completion.py",
                "test_failing_acceptance_blocks_done",
            ),
            _ev(
                "unit_test",
                "tests/test_hooks.py",
                "test_completion_hook_blocks_failed_task",
            ),
        ),
    ),
    Criterion(
        6,
        SPEC_STATEMENTS[5],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_failures.py",
                "test_second_identical_failure_requests_diagnosis",
            ),
        ),
    ),
    Criterion(
        7,
        SPEC_STATEMENTS[6],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_hooks.py",
                "test_precompact_checkpoints_state_and_candidates",
            ),
            _ev(
                "unit_test",
                "tests/test_runtime_claude.py",
                "test_compaction_order_is_explicit",
            ),
        ),
    ),
    Criterion(
        8,
        SPEC_STATEMENTS[7],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_runtime_cursor.py",
                "test_cursor_sandbox_is_not_disabled",
            ),
            _ev("generated_config", "tests/golden/cursor/sandbox.json"),
        ),
    ),
    Criterion(
        9,
        SPEC_STATEMENTS[8],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_validate.py",
                "test_ssh_and_scp_urls_in_core_fail",
            ),
            _ev("validator", "src/nexus_harness/validate.py"),
        ),
    ),
    Criterion(
        10,
        SPEC_STATEMENTS[9],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_validate.py",
                "test_constitution_model_names_fail",
            ),
            _ev("validator", "core/constitution.md"),
        ),
    ),
    Criterion(
        11,
        SPEC_STATEMENTS[10],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_skill_contracts.py",
                "test_vendor_lock_parses_with_real_revisions",
            ),
            _ev("release_manifest", "upstream/vendor-lock.json"),
            _ev("release_manifest", "harness.lock"),
        ),
    ),
    Criterion(
        12,
        SPEC_STATEMENTS[11],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_compile.py",
                "test_second_render_is_byte_identical",
            ),
            _ev(
                "golden_test",
                "tests/test_golden_adapters.py",
                "test_rendered_files_match_reviewed_snapshots_byte_for_byte",
            ),
            _ev(
                "unit_test",
                "tests/test_release.py",
                "test_release_manifest_is_reproducible",
            ),
        ),
    ),
    Criterion(
        13,
        SPEC_STATEMENTS[12],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_quality.py",
                "test_lower_is_better_ratchet_rejects_regression",
            ),
            _ev(
                "unit_test",
                "tests/test_security.py",
                "test_report_to_dict_matches_schema_contract",
            ),
            _ev("security_scan", "core/security/security-report.schema.json"),
            _ev("release_manifest", "core/quality/quality-report.schema.json"),
        ),
    ),
    Criterion(
        14,
        SPEC_STATEMENTS[13],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_visual.py",
                "test_visual_evidence_is_stale_after_ui_diff_changes",
            ),
            _ev(
                "eval_case",
                "evals/cases/visual-stale-evidence.json",
                "visual-stale-evidence",
            ),
        ),
    ),
    Criterion(
        15,
        SPEC_STATEMENTS[14],
        "ACTIVATION_REQUIRED",
        True,
        (
            _ev(
                "unit_test",
                "tests/test_ci_vps_files.py",
                "test_required_files_exist",
            ),
            _ev(
                "doctor_check",
                "src/nexus_harness/doctor.py",
                "ci-profile",
                "live VPS is not probed; missing runner token is activation",
            ),
        ),
    ),
    Criterion(
        16,
        SPEC_STATEMENTS[15],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_affected.py",
                "test_web_change_does_not_build_server_image",
            ),
            _ev(
                "unit_test",
                "tests/test_cli.py",
                "test_ci_affected_writes_plan_with_fake_git",
            ),
        ),
    ),
    Criterion(
        17,
        SPEC_STATEMENTS[16],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_deploy_contract.py",
                "test_valid_service_and_digest_accepted",
            ),
            _ev(
                "eval_case",
                "evals/cases/production-deploy-dry-run.json",
                "production-deploy-dry-run",
            ),
            _ev(
                "unit_test",
                "tests/test_pull_request.py",
                "test_complete_issue_uses_closes_reference",
            ),
        ),
    ),
    Criterion(
        18,
        SPEC_STATEMENTS[17],
        "ACTIVATION_REQUIRED",
        True,
        (
            _ev(
                "unit_test",
                "tests/test_governance_integration.py",
                "test_bounded_bug_governance_flow",
            ),
            _ev(
                "unit_test",
                "tests/test_project_sync.py",
                "test_stage_5_maps_to_in_progress",
            ),
            _ev(
                "eval_case",
                "evals/cases/github-bounded-bug-governance.json",
                "github-bounded-bug-governance",
            ),
            _ev(
                "doctor_check",
                "src/nexus_harness/doctor.py",
                "github",
                "live GitHub Project IDs stay in user configuration",
            ),
        ),
    ),
    Criterion(
        19,
        SPEC_STATEMENTS[18],
        "ACTIVATION_REQUIRED",
        True,
        (
            _ev(
                "unit_test",
                "tests/test_incidents.py",
                "test_same_error_location_has_stable_fingerprint",
            ),
            _ev(
                "eval_case",
                "evals/cases/runtime-incident-dedup.json",
                "runtime-incident-dedup",
            ),
            _ev(
                "doctor_check",
                "src/nexus_harness/doctor.py",
                "posthog",
                "live PostHog remains unactivated",
            ),
        ),
    ),
    Criterion(
        20,
        SPEC_STATEMENTS[19],
        "PASS",
        False,
        (
            _ev(
                "unit_test",
                "tests/test_doctor.py",
                "test_local_fixture_covers_required_checks_without_false_fail",
            ),
            _ev(
                "unit_test",
                "tests/test_evals.py",
                "test_deterministic_suite_passes_without_model_calls",
            ),
            _ev(
                "unit_test",
                "tests/test_install.py",
                "test_disposable_home_install_parses_adapters_and_never_touches_real_homes",
            ),
            _ev("golden_test", "tests/golden/claude/settings.json"),
            _ev("golden_test", "tests/golden/codex/config.toml"),
        ),
    ),
)


def _missing_evidence(root: Path, item: Criterion) -> list[str]:
    missing: list[str] = []
    if not item.evidence:
        missing.append("no evidence declared")
        return missing
    for ev in item.evidence:
        if ev.kind not in EVIDENCE_KINDS:
            missing.append(f"{ev.kind} is not an allowed evidence kind")
            continue
        path = root / ev.path
        if not path.exists():
            missing.append(f"missing {ev.path}")
            continue
        if ev.kind == "unit_test" or (
            ev.kind == "golden_test" and ev.selector.startswith("test_")
        ):
            text = path.read_text(encoding="utf-8")
            needle = f"def {ev.selector}("
            if ev.selector and needle not in text:
                missing.append(f"{ev.path} has no {needle.strip()}")
        elif ev.kind == "eval_case":
            try:
                payload = __import__("json").loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                missing.append(f"{ev.path} is not valid JSON: {exc}")
                continue
            name = str(payload.get("name") or "")
            if ev.selector and name != ev.selector:
                missing.append(f"{ev.path} name {name!r} != {ev.selector!r}")
        elif ev.kind == "migration_report_field":
            text = path.read_text(encoding="utf-8")
            if ev.selector and ev.selector not in text:
                missing.append(f"{ev.path} missing field {ev.selector!r}")
        elif ev.kind == "doctor_check":
            text = path.read_text(encoding="utf-8")
            if ev.selector and ev.selector not in text:
                missing.append(f"{ev.path} missing doctor check {ev.selector!r}")
    return missing


def evaluate_matrix(
    root: Path,
    criteria: Sequence[Criterion] | None = None,
) -> MatrixReport:
    root = Path(root)
    items = tuple(criteria) if criteria is not None else SUCCESS_CRITERIA
    results: list[CriterionResult] = []
    for item in items:
        if item.expected_status not in ALLOWED_STATES:
            missing = (f"state {item.expected_status!r} is not allowed",)
            status = "FAIL"
        else:
            missing = tuple(_missing_evidence(root, item))
            if missing:
                status = "FAIL"
            elif item.live and item.expected_status == "PASS":
                missing = ("live criterion cannot be marked PASS",)
                status = "FAIL"
            else:
                status = item.expected_status
        results.append(
            CriterionResult(
                id=item.id,
                statement=item.statement,
                status=status,
                expected_status=item.expected_status,
                live=item.live,
                evidence=item.evidence,
                missing=missing,
            )
        )
    fail_count = sum(1 for result in results if result.status == "FAIL")
    activation = tuple(
        result.id for result in results if result.status == "ACTIVATION_REQUIRED"
    )
    gate = "FAIL" if fail_count else "PASS"
    summary = (
        f"{gate}: {len(results)} criteria, {fail_count} FAIL, "
        f"{len(activation)} ACTIVATION_REQUIRED"
    )
    return MatrixReport(
        gate=gate,
        results=tuple(results),
        fail_count=fail_count,
        summary=summary,
    )


def format_matrix_markdown(report: MatrixReport) -> str:
    lines = [
        "| # | Criterion | Status | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for result in report.results:
        sources = "; ".join(
            f"{ev.kind}:{ev.path}" + (f"#{ev.selector}" if ev.selector else "")
            for ev in result.evidence
        )
        if result.missing:
            sources += " — missing: " + "; ".join(result.missing)
        lines.append(
            f"| {result.id} | {result.statement} | {result.status} | {sources} |"
        )
    lines.append("")
    lines.append(f"Local release gate: **{report.gate}** ({report.summary})")
    return "\n".join(lines) + "\n"
