"""Deterministic Nexus policy evals. No live models. No remote mutation."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from unittest.mock import patch

from nexus_harness.affected import load_ci_profile, resolve_affected
from nexus_harness.completion import evaluate_completion
from nexus_harness.config import load_toml
from nexus_harness.deploy_contract import DeployError, parse_deploy_argv
from nexus_harness.graph import GraphNode, TaskGraph
from nexus_harness.hierarchy import apply_hierarchy, tracking_shape
from nexus_harness.incident_policy import classify_incident
from nexus_harness.memory.freshness import (
    TruthStrength,
    compute_memory_freshness,
    resolve_contradiction,
)
from nexus_harness.memory.models import MemoryRecord
from nexus_harness.pull_request import ready_to_merge
from nexus_harness.quality import load_quality_profile
from nexus_harness.security import normalize_trivy
from nexus_harness.state import TaskState
from nexus_harness.tracking import ensure_issue, tracking_required
from nexus_harness.visual import (
    bind_visual_requirement,
    is_visual_required,
    visual_completion_reasons,
)
from nexus_harness.workflow import advance_stage

MODEL_SKIP_REASON = (
    "model-quality evals SKIP: release PASS must not depend on "
    "Claude/Codex/Cursor/Kimi/Grok/paid inference"
)

_DEFAULT_SERVICES = {
    "services": {
        "web": {
            "compose_file": "/opt/app/docker-compose.yml",
            "project_dir": "/opt/app",
            "digest_var": "WEB_IMAGE_DIGEST",
            "image": "ghcr.io/example/app-web",
            "health_url": "http://127.0.0.1:8080/health",
        }
    }
}

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class EvalCase:
    name: str
    classification: dict[str, Any]
    input: dict[str, Any]
    expect: dict[str, Any]
    path: Path


@dataclass(frozen=True)
class EvalCaseResult:
    name: str
    status: str
    failures: tuple[str, ...] = ()
    model_eval: str = "SKIP"
    model_eval_reason: str = MODEL_SKIP_REASON
    observations: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "failures": list(self.failures),
            "model_eval": self.model_eval,
            "model_eval_reason": self.model_eval_reason,
        }


@dataclass(frozen=True)
class EvalReport:
    gate: str
    results: tuple[EvalCaseResult, ...] = ()
    summary: str = ""
    model_eval: str = "SKIP"
    model_eval_reason: str = MODEL_SKIP_REASON

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "summary": self.summary,
            "model_eval": self.model_eval,
            "model_eval_reason": self.model_eval_reason,
            "results": [item.to_dict() for item in self.results],
        }


class _NullGitHub:
    def api_graphql(self, *args, **kwargs):
        raise AssertionError("remote mutation is forbidden in evals")

    def create_issue(self, *args, **kwargs):
        raise AssertionError("remote mutation is forbidden in evals")

    def edit_issue(self, *args, **kwargs):
        raise AssertionError("remote mutation is forbidden in evals")

    def find_issue(self, *args, **kwargs):
        return None

    def view_issue(self, *args, **kwargs):
        return None


def load_cases(directory: Path) -> tuple[EvalCase, ...]:
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"eval cases directory not found: {root}")
    cases: list[EvalCase] = []
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"eval case must be a JSON object: {path}")
        name = str(payload.get("name") or path.stem)
        cases.append(
            EvalCase(
                name=name,
                classification=dict(payload.get("classification") or {}),
                input=dict(payload.get("input") or {}),
                expect=dict(payload.get("expect") or {}),
                path=path,
            )
        )
    return tuple(cases)


def format_evals_report(report: EvalReport) -> str:
    lines = [f"nexus evals  gate={report.gate}", ""]
    for item in report.results:
        lines.append(f"{item.status:8} {item.name}")
        for failure in item.failures:
            lines.append(f"         {failure}")
    lines.append(f"{report.model_eval:8} model-quality")
    lines.append(f"         {report.model_eval_reason}")
    return "\n".join(lines) + "\n"


def run_evals(
    cases_dir: Path,
    *,
    repo_root: Path | None = None,
    github: object | None = None,
    include_model: bool = False,
) -> EvalReport:
    del include_model  # optional layer; never required for release PASS
    cases_path = Path(cases_dir)
    root = Path(repo_root) if repo_root is not None else _infer_repo_root(cases_path)
    results = tuple(
        _run_case(case, repo_root=root, github=github)
        for case in load_cases(cases_path)
    )
    failed = [item for item in results if item.status != "PASS"]
    gate = "FAIL" if failed else "PASS"
    summary = f"{gate}: {len(results) - len(failed)}/{len(results)} passed; model-quality SKIP"
    return EvalReport(
        gate=gate,
        results=results,
        summary=summary,
        model_eval="SKIP",
        model_eval_reason=MODEL_SKIP_REASON,
    )


def _infer_repo_root(cases_dir: Path) -> Path:
    resolved = cases_dir.resolve()
    if resolved.name == "cases" and resolved.parent.name == "evals":
        return resolved.parent.parent
    return _REPO_ROOT


def _run_case(
    case: EvalCase, *, repo_root: Path, github: object | None
) -> EvalCaseResult:
    failures: list[str] = []
    gh = github if github is not None else _NullGitHub()
    classification = case.classification
    data = case.input
    expect = case.expect
    work_type = str(classification.get("work_type") or "")
    scope = str(classification.get("scope") or "")
    mutable = classification.get("mutable")
    profile_name = str(classification.get("quality_profile") or "standard")
    profile = load_quality_profile(profile_name)

    tracking_is_required = tracking_required(work_type, mutable)
    shape = list(
        tracking_shape(
            scope,
            work_type,
            independent_deliverables=classification.get("independent_deliverables"),
        )
    )
    hierarchy = apply_hierarchy(
        gh,
        repo=str(classification.get("repository") or "eval/repo"),
        scope=scope,
        work_type=work_type,
        parent=data.get("parent_issue"),
        children=tuple(data.get("child_issues") or ()),
        parent_id=data.get("parent_id"),
        child_ids=tuple(data.get("child_ids") or ()),
        independent_deliverables=classification.get("independent_deliverables"),
        authorize_remote_mutation=bool(data.get("authorize_remote_mutation", False)),
    )
    task_state = TaskState.new(case.name, "eval/repo")
    tracking = ensure_issue(
        task_state,
        gh,
        title=case.name,
        work_type=work_type or "change",
        authorize_remote_mutation=False,
    )

    checks: list[str] = []
    components: list[str] = []
    if data.get("changed_paths") and data.get("ci_profile"):
        ci_path = Path(data["ci_profile"])
        if not ci_path.is_absolute():
            ci_path = repo_root / ci_path
        ci = load_ci_profile(ci_path)
        plan = resolve_affected(
            list(data["changed_paths"]),
            ci.components,
            global_paths=ci.global_paths,
        )
        checks = list(plan.checks)
        components = list(plan.components)

    conflicts: list[list[str]] = []
    ready: list[str] = []
    node_ids: list[str] = []
    if data.get("graph_nodes"):
        nodes = [GraphNode.from_dict(item) for item in data["graph_nodes"]]
        graph = TaskGraph(nodes)
        node_ids = [node.id for node in nodes]
        conflicts = [list(pair) for pair in sorted(graph.conflicts())]
        ready = sorted(node.id for node in graph.ready_nodes())

    security_gate = None
    if "trivy" in data:
        security_gate = normalize_trivy(data["trivy"]).gate

    raw_state = data.get("state")
    state = dict(raw_state) if isinstance(raw_state, dict) else {}
    has_state = isinstance(raw_state, dict) or bool(data.get("bind_visual"))
    if has_state and "tracking_required" not in state:
        state["tracking_required"] = tracking_is_required
    if data.get("bind_visual") and data.get("ci_profile"):
        ci_path = Path(data["ci_profile"])
        if not ci_path.is_absolute():
            ci_path = repo_root / ci_path
        ci = load_ci_profile(ci_path)
        bind_visual_requirement(
            state, {"frontend": ci.frontend}, data.get("changed_paths")
        )

    visual_required = is_visual_required(state) if has_state else False
    visual_reasons = visual_completion_reasons(state) if has_state else []
    completion_state = (
        state
        if has_state
        else {
            "tracking_required": tracking_is_required,
            "acceptance": [],
        }
    )
    completion = evaluate_completion(completion_state)
    merge = ready_to_merge(completion_state)

    incident_action = None
    if "incident" in data:
        inc = data["incident"]
        incident_action = classify_incident(
            occurrences=inc.get("occurrences"),
            affected_users=inc.get("affected_users"),
            regression=bool(inc.get("regression")),
            fatal=bool(inc.get("fatal")),
            fingerprint=inc.get("fingerprint"),
            open_issues=inc.get("open_issues") or (),
            security_adjacent=bool(inc.get("security_adjacent")),
        ).action

    freshness = None
    contradiction_winner = None
    if "memory" in data:
        mem = data["memory"]
        if mem.get("record"):
            record = MemoryRecord.from_json_dict(mem["record"])
            changed = mem.get("changed_paths")
            if changed is not None:
                with patch(
                    "nexus_harness.memory.freshness._changed_paths_since",
                    return_value=tuple(changed),
                ):
                    freshness = compute_memory_freshness(repo_root, record).status.value
            else:
                freshness = compute_memory_freshness(repo_root, record).status.value
        if mem.get("contradiction"):
            items = [
                (str(item["id"]), TruthStrength[str(item["authority"])])
                for item in mem["contradiction"]
            ]
            contradiction_winner = resolve_contradiction(items).winner

    production = load_toml(repo_root / "core" / "policies" / "production.toml")
    deploy_cfg = production.get("deploy") or {}
    latest_rejected = None
    digest_accepted = None
    if "deploy" in data or "mutable_latest_tag" in set(expect.get("forbidden") or ()):
        services = (data.get("deploy") or {}).get("services") or _DEFAULT_SERVICES
        service = str((data.get("deploy") or {}).get("service") or "web")
        digest = str((data.get("deploy") or {}).get("digest") or "sha256:" + ("a" * 64))
        try:
            parse_deploy_argv(["deploy", service, digest], services=services)
            digest_accepted = True
        except DeployError:
            digest_accepted = False
        try:
            parse_deploy_argv(["deploy", service, "latest"], services=services)
            latest_rejected = False
        except DeployError:
            latest_rejected = True

    implement_blocked = None
    if data.get("try_implement"):
        probe = TaskState.new(f"{case.name}-implement", "eval/repo")
        probe.intent = str(classification.get("intent") or "change")
        probe.stage = 4
        probe.tracking_required = tracking_is_required
        try:
            advance_stage(probe, 5)
            implement_blocked = False
        except ValueError:
            implement_blocked = True

    observations = {
        "classification": classification,
        "tracking": {
            "required": tracking_is_required,
            "shape": shape,
            "remote_mutation": bool(hierarchy.linked or tracking.created),
        },
        "graph": {
            "nodes": node_ids,
            "checks": checks,
            "components": components,
            "conflicts": conflicts,
            "ready": ready,
        },
        "quality_profile": {"name": profile_name, **profile},
        "approvals": {
            "required": list(state.get("approvals_required") or []),
            "recorded": list(state.get("approvals_recorded") or [])
            if not isinstance(state.get("approvals_recorded"), bool)
            else state.get("approvals_recorded"),
        },
        "security": {"gate": security_gate},
        "visual": {"required": visual_required, "reasons": visual_reasons},
        "incident": {"action": incident_action},
        "memory": {
            "freshness": freshness,
            "contradiction_winner": contradiction_winner,
        },
        "completion": {
            "status": completion.status,
            "reasons": list(completion.reasons),
        },
        "ship": {
            "ready": completion.status == "READY_TO_SHIP"
            and merge.status == "READY_TO_MERGE",
            "requires_explicit_approval": bool(
                deploy_cfg.get("requires_explicit_gate")
            ),
            "requires_immutable_digest": bool(deploy_cfg.get("identify_by_digest"))
            and bool(deploy_cfg.get("immutable_artifacts")),
            "latest_rejected": latest_rejected,
            "digest_accepted": digest_accepted,
            "mutable_latest_tag_forbidden": bool(
                deploy_cfg.get("mutable_latest_tag_forbidden")
            ),
        },
        "implement_blocked": implement_blocked,
    }

    failures.extend(
        _compare_expect(expect, observations, hierarchy_linked=hierarchy.linked)
    )
    status = "FAIL" if failures else "PASS"
    return EvalCaseResult(
        name=case.name,
        status=status,
        failures=tuple(failures),
        observations=observations,
    )


def _compare_expect(
    expect: dict[str, Any],
    actual: dict[str, Any],
    *,
    hierarchy_linked: bool,
) -> list[str]:
    failures: list[str] = []
    failures.extend(
        _compare_mapping(
            "classification", expect.get("classification"), actual["classification"]
        )
    )
    failures.extend(_compare_tracking(expect.get("tracking"), actual["tracking"]))
    failures.extend(_compare_graph(expect.get("graph"), actual["graph"]))
    failures.extend(
        _compare_quality(expect.get("quality_profile"), actual["quality_profile"])
    )
    failures.extend(_compare_approvals(expect.get("approvals"), actual["approvals"]))
    failures.extend(
        _compare_mapping("security", expect.get("security"), actual["security"])
    )
    failures.extend(_compare_visual(expect.get("visual"), actual["visual"]))
    failures.extend(
        _compare_mapping("incident", expect.get("incident"), actual["incident"])
    )
    failures.extend(_compare_mapping("memory", expect.get("memory"), actual["memory"]))
    failures.extend(_compare_completion(expect.get("completion"), actual["completion"]))
    failures.extend(_compare_ship(expect.get("ship"), actual["ship"]))
    failures.extend(
        _compare_forbidden(
            expect.get("forbidden") or [],
            actual,
            hierarchy_linked=hierarchy_linked,
        )
    )
    return failures


def _compare_tracking(expected, actual) -> list[str]:
    if not expected:
        return []
    failures = []
    if "required" in expected and bool(expected["required"]) != bool(
        actual["required"]
    ):
        failures.append(
            f"tracking.required: expected {expected['required']!r} got {actual['required']!r}"
        )
    if "shape" in expected and list(expected["shape"]) != list(actual["shape"]):
        failures.append(
            f"tracking.shape: expected {list(expected['shape'])!r} got {list(actual['shape'])!r}"
        )
    return failures


def _compare_graph(expected, actual) -> list[str]:
    if not expected:
        return []
    failures = []
    if "checks" in expected:
        missing = [item for item in expected["checks"] if item not in actual["checks"]]
        if missing:
            failures.append(f"graph.checks missing {missing}; got {actual['checks']}")
    if "components" in expected:
        missing = [
            item for item in expected["components"] if item not in actual["components"]
        ]
        if missing:
            failures.append(
                f"graph.components missing {missing}; got {actual['components']}"
            )
    if "nodes" in expected:
        missing = [item for item in expected["nodes"] if item not in actual["nodes"]]
        if missing:
            failures.append(f"graph.nodes missing {missing}; got {actual['nodes']}")
    if "conflicts" in expected and _norm_pairs(expected["conflicts"]) != _norm_pairs(
        actual["conflicts"]
    ):
        failures.append(
            f"graph.conflicts: expected {expected['conflicts']!r} got {actual['conflicts']!r}"
        )
    if "ready" in expected and sorted(expected["ready"]) != sorted(actual["ready"]):
        failures.append(
            f"graph.ready: expected {expected['ready']!r} got {actual['ready']!r}"
        )
    return failures


def _norm_pairs(pairs) -> list[tuple[str, str]]:
    return sorted(tuple(sorted(pair)) for pair in pairs)


def _compare_quality(expected, actual) -> list[str]:
    if not expected:
        return []
    failures = []
    for key, value in expected.items():
        if actual.get(key) != value:
            failures.append(
                f"quality_profile.{key}: expected {value!r} got {actual.get(key)!r}"
            )
    return failures


def _compare_approvals(expected, actual) -> list[str]:
    if not expected:
        return []
    failures = []
    if "required" in expected and list(expected["required"]) != list(
        actual["required"]
    ):
        failures.append(
            f"approvals.required: expected {expected['required']!r} got {actual['required']!r}"
        )
    return failures


def _compare_visual(expected, actual) -> list[str]:
    if not expected:
        return []
    failures = []
    if "required" in expected and bool(expected["required"]) != bool(
        actual["required"]
    ):
        failures.append(
            f"visual.required: expected {expected['required']!r} got {actual['required']!r}"
        )
    if expected.get("reasons_any"):
        blob = " ".join(actual.get("reasons") or [])
        if not any(token in blob for token in expected["reasons_any"]):
            failures.append(
                f"visual.reasons missing {expected['reasons_any']!r}; got {actual.get('reasons')}"
            )
    return failures


def _compare_completion(expected, actual) -> list[str]:
    if not expected:
        return []
    failures = []
    if "status" in expected and expected["status"] != actual["status"]:
        failures.append(
            f"completion.status: expected {expected['status']!r} got {actual['status']!r}"
        )
    if expected.get("reasons_any"):
        blob = " ".join(actual.get("reasons") or [])
        if not any(token in blob for token in expected["reasons_any"]):
            failures.append(
                f"completion.reasons missing {expected['reasons_any']!r}; got {actual.get('reasons')}"
            )
    return failures


def _compare_ship(expected, actual) -> list[str]:
    if not expected:
        return []
    failures = []
    for key in (
        "ready",
        "requires_explicit_approval",
        "requires_immutable_digest",
        "latest_rejected",
        "digest_accepted",
    ):
        if key in expected and expected[key] != actual.get(key):
            failures.append(
                f"ship.{key}: expected {expected[key]!r} got {actual.get(key)!r}"
            )
    return failures


def _compare_mapping(label: str, expected, actual) -> list[str]:
    if not expected:
        return []
    failures = []
    for key, value in expected.items():
        if value is None and actual.get(key) is None:
            continue
        if actual.get(key) != value:
            failures.append(
                f"{label}.{key}: expected {value!r} got {actual.get(key)!r}"
            )
    return failures


def _compare_forbidden(
    forbidden: Sequence[str],
    actual: dict[str, Any],
    *,
    hierarchy_linked: bool,
) -> list[str]:
    failures = []
    names = {str(item) for item in forbidden}
    if "remote_mutation" in names and (
        hierarchy_linked or actual["tracking"]["remote_mutation"]
    ):
        failures.append("forbidden remote_mutation occurred")
    if "live_model" in names or "paid_inference" in names:
        pass  # never invoked
    if (
        "mutable_latest_tag" in names
        and actual["ship"].get("latest_rejected") is not True
    ):
        failures.append("forbidden mutable_latest_tag was not rejected")
    if "ship_without_approval" in names and actual["ship"]["ready"]:
        failures.append("forbidden ship_without_approval occurred")
    if (
        "implement_without_acceptance" in names
        and actual.get("implement_blocked") is False
    ):
        failures.append("forbidden implement_without_acceptance occurred")
    if "empty_child_issues" in names and len(actual["tracking"]["shape"]) > 1:
        failures.append(
            f"forbidden empty_child_issues: shape {actual['tracking']['shape']}"
        )
    if (
        "auto_create_incident" in names
        and actual["incident"].get("action") == "CREATE_ISSUE"
    ):
        failures.append("forbidden auto_create_incident occurred")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cases = Path(args[0]) if args else Path("evals/cases")
    report = run_evals(cases)
    print(format_evals_report(report))
    return 0 if report.gate == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
