from dataclasses import dataclass, field
from pathlib import Path
import tomllib

from nexus_harness.evidence import Evidence
from nexus_harness.visual import visual_completion_reasons

# Mutable completion evidence is commit-bound: a non-empty base_commit is required
# unless the record is explicitly commit-independent (static policy-file checks).
# Visual screenshots bound to diff_hash are always commit-bound.


_BLOCKING_FINDINGS = frozenset({"blocker", "high"})
_COMPLETION_POLICY = (
    Path(__file__).resolve().parents[2] / "core" / "workflow" / "completion.toml"
)


@dataclass
class CompletionResult:
    status: str
    reasons: list[str] = field(default_factory=list)


def evaluate_completion(state) -> CompletionResult:
    reasons: list[str] = []
    current = _get(state, "current_diff_hash")

    if _get(state, "tracking_required") and not _has_issue(state):
        reasons.append("issue required when tracking_required")

    if _required_approvals_missing(state):
        reasons.append("required approvals are not recorded")

    acceptance = list(_get(state, "acceptance") or [])
    if not acceptance or any(_item_status(item) != "PASS" for item in acceptance):
        reasons.append("acceptance criteria not PASS")

    if _gate(state, "quality_gate") != "PASS":
        reasons.append("quality_gate is not PASS")
    if _gate(state, "security_gate") != "PASS":
        reasons.append("security_gate is not PASS")
    if not _gate_fresh(state, "quality_gate", current):
        reasons.append("quality report is not fresh")
    if not _gate_fresh(state, "security_gate", current):
        reasons.append("security report is not fresh")

    review = _gate(state, "review_gate")
    if review == "SKIP":
        if not _skip_reason(state):
            reasons.append("review_gate SKIP needs skip_reason")
    elif review != "PASS":
        reasons.append("review_gate is not PASS")

    if _confirmed_blocker_or_high(state):
        reasons.append("confirmed blocker/high finding")

    if not _acceptance_evidence_fresh(state, current):
        reasons.append("acceptance evidence is not fresh")

    verified = _get(state, "verified_diff_hash")
    reviewed = _get(state, "reviewed_diff_hash")
    if not (current and current == verified == reviewed):
        reasons.append("verified_diff_hash != current_diff_hash != reviewed_diff_hash")

    reasons.extend(visual_completion_reasons(state, current))

    if _mutable_evidence_missing_base_commit(state):
        reasons.append("mutable evidence is missing base_commit")

    if reasons:
        return CompletionResult(status="FAIL", reasons=reasons)
    return CompletionResult(status="READY_TO_SHIP", reasons=[])


def _load_completion_policy() -> dict:
    with _COMPLETION_POLICY.open("rb") as policy_file:
        return tomllib.load(policy_file)


def _required_approvals_missing(state) -> bool:
    policy = _load_completion_policy()
    if not policy.get("require", {}).get("required_approvals_recorded", False):
        return False
    required = _get(state, "approvals_required") or []
    recorded = _get(state, "approvals_recorded")
    if recorded is None:
        recorded = _get(state, "approvals") or []
    if isinstance(recorded, bool):
        return not recorded
    if isinstance(required, dict):
        required = required.keys()
    if isinstance(recorded, dict):
        recorded = recorded.keys()
    try:
        return not set(required).issubset(set(recorded))
    except TypeError:
        return True


def promote_acceptance(state, evidence, ledger=None):
    """Mark a criterion PASS only from recorded, fresh, passing evidence."""
    candidate = _as_evidence(evidence)
    if candidate is None:
        raise ValueError("evidence does not exist")
    record = _lookup_evidence(state, candidate.id)
    if record is None:
        record = _lookup_ledger(ledger, candidate.id)
    if record is None:
        raise ValueError("evidence is not recorded")
    if record.exit_code != 0:
        raise ValueError("evidence exit_code is not 0")
    current = _get(state, "current_diff_hash")
    if record.diff_hash != current:
        raise ValueError("evidence diff_hash does not match current_diff_hash")
    if not _change_head_fresh(state, record):
        raise ValueError("evidence change_head_sha does not match change_head_sha")
    if not _is_commit_independent(record) and not _valid_base_commit(
        record.base_commit
    ):
        raise ValueError("mutable evidence is missing base_commit")

    target = _target_criterion(state, record)
    if target is None:
        raise ValueError("no acceptance criterion to promote")
    _set_item_status(target, "PASS")
    _set_item_evidence(target, record.id)
    return state


def _get(state, key, default=None):
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _has_issue(state) -> bool:
    issue = _get(state, "issue")
    try:
        return issue is not None and int(issue) >= 1
    except (TypeError, ValueError):
        return False


def _gate(state, key):
    value = _get(state, key)
    if key in {"quality_gate", "security_gate"}:
        report = _structured_report(value)
        if report is None:
            return None
        return report.get("gate")
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("gate")
    return getattr(value, "gate", value)


def _structured_report(value) -> dict | None:
    if value is None or isinstance(value, str):
        return None
    if isinstance(value, dict):
        if "gate" not in value:
            return None
        return value
    gate = getattr(value, "gate", None)
    if gate is None:
        return None
    return {
        "gate": gate,
        "diff_hash": getattr(value, "diff_hash", None),
        "change_head_sha": getattr(value, "change_head_sha", None),
        "checkout_sha": getattr(value, "checkout_sha", None),
    }


def _report_diff_hash(value):
    report = _structured_report(value)
    if report is None:
        return None
    return report.get("diff_hash")


def _change_head(state) -> str | None:
    raw = _get(state, "change_head_sha")
    text = str(raw or "").strip()
    return text or None


def _record_change_head(record) -> str | None:
    if record is None:
        return None
    if isinstance(record, dict):
        raw = record.get("change_head_sha")
    else:
        raw = getattr(record, "change_head_sha", None)
    text = str(raw or "").strip()
    return text or None


def _change_head_fresh(state, record) -> bool:
    target = _change_head(state)
    if not target:
        return True
    if record is not None and _is_commit_independent(record):
        return True
    bound = _record_change_head(record)
    return bool(bound) and bound == target


def _gate_fresh(state, key, current_diff_hash) -> bool:
    value = _get(state, key)
    report = _structured_report(value)
    if report is None:
        return False
    if not _change_head_fresh(state, report):
        return False
    report_hash = _report_diff_hash(value)
    if report_hash is None or str(report_hash).strip() == "":
        return False
    if not current_diff_hash:
        return False
    return str(report_hash) == str(current_diff_hash)


def _skip_reason(state) -> str:
    reason = _get(state, "skip_reason")
    if reason is None:
        return ""
    return str(reason).strip()


def _item_status(item) -> str:
    if isinstance(item, dict):
        return item.get("status", "FAIL")
    return getattr(item, "status", "FAIL")


def _item_evidence_id(item):
    raw = (
        item.get("evidence")
        if isinstance(item, dict)
        else getattr(item, "evidence", None)
    )
    if isinstance(raw, str):
        return raw
    record = _as_evidence(raw)
    return None if record is None else record.id


def _set_item_status(item, status: str) -> None:
    if isinstance(item, dict):
        item["status"] = status
    else:
        item.status = status


def _set_item_evidence(item, evidence_id: str) -> None:
    if isinstance(item, dict):
        item["evidence"] = evidence_id
    else:
        item.evidence = evidence_id


def _as_evidence(value) -> Evidence | None:
    if value is None:
        return None
    if isinstance(value, Evidence):
        return value
    if isinstance(value, dict) and value.get("id"):
        return Evidence(
            id=str(value["id"]),
            command=str(value.get("command") or ""),
            exit_code=int(value.get("exit_code", 1)),
            diff_hash=str(value.get("diff_hash") or ""),
            base_commit=str(value.get("base_commit") or ""),
            summary=str(value.get("summary") or ""),
            commit_independent=bool(value.get("commit_independent")),
            change_head_sha=(str(value["change_head_sha"]).strip() or None)
            if value.get("change_head_sha")
            else None,
            checkout_sha=(str(value["checkout_sha"]).strip() or None)
            if value.get("checkout_sha")
            else None,
        )
    return None


def _ledger(state) -> list[Evidence]:
    return _evidence_records(_get(state, "evidence"))


def _evidence_records(raw) -> list[Evidence]:
    raw = raw or []
    if isinstance(raw, Evidence):
        raw = [raw]
    items = []
    for item in raw:
        record = _as_evidence(item)
        if record is not None:
            items.append(record)
    return items


def _lookup_evidence(state, evidence_id: str | None) -> Evidence | None:
    return _lookup_ledger(_ledger(state), evidence_id)


def _lookup_ledger(ledger, evidence_id: str | None) -> Evidence | None:
    if not evidence_id:
        return None
    for record in _evidence_records(ledger):
        if record.id == evidence_id:
            return record
    return None


def _acceptance_evidence_fresh(state, current_diff_hash) -> bool:
    if not current_diff_hash:
        return False
    passed = [
        item
        for item in list(_get(state, "acceptance") or [])
        if _item_status(item) == "PASS"
    ]
    if not passed:
        return True
    for item in passed:
        record = _lookup_evidence(state, _item_evidence_id(item))
        if record is None or record.exit_code != 0:
            return False
        if record.diff_hash != current_diff_hash:
            return False
        if not _change_head_fresh(state, record):
            return False
        if not _is_commit_independent(record) and not _valid_base_commit(
            record.base_commit
        ):
            return False
    return True


def _confirmed_blocker_or_high(state) -> bool:
    for finding in _get(state, "findings") or []:
        if not _finding_confirmed(finding):
            continue
        if _finding_severity(finding) in _BLOCKING_FINDINGS:
            return True
    return False


def _finding_confirmed(finding) -> bool:
    if isinstance(finding, dict):
        status = finding.get("status")
        if status is not None and str(status).strip():
            return str(status).strip().lower() == "confirmed"
        return bool(finding.get("confirmed"))
    status = getattr(finding, "status", None)
    if status is not None and str(status).strip():
        return str(status).strip().lower() == "confirmed"
    return bool(getattr(finding, "confirmed", False))


def _finding_severity(finding) -> str:
    if isinstance(finding, dict):
        raw = finding.get("severity")
    else:
        raw = getattr(finding, "severity", "")
    return str(raw or "").strip().lower()


def _target_criterion(state, record: Evidence):
    items = list(_get(state, "acceptance") or [])
    for item in items:
        if _item_evidence_id(item) == record.id:
            return item
    for item in items:
        if _item_status(item) != "PASS":
            return item
    return None


COMMIT_INDEPENDENT_COMMANDS = frozenset({"static-policy", "policy-file"})


def _valid_base_commit(value) -> bool:
    return bool(str(value or "").strip())


def _is_commit_independent(record: Evidence) -> bool:
    if bool(getattr(record, "commit_independent", False)):
        return True
    command = str(getattr(record, "command", "") or "").strip().lower()
    return command in COMMIT_INDEPENDENT_COMMANDS


def _mutable_evidence_missing_base_commit(state) -> bool:
    for record in _ledger(state):
        if _is_commit_independent(record):
            continue
        if not _valid_base_commit(record.base_commit):
            return True
    return False
