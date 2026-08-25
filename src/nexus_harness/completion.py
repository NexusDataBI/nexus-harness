from dataclasses import dataclass, field

from nexus_harness.evidence import Evidence

_BLOCKING_FINDINGS = frozenset({"blocker", "high"})


@dataclass
class CompletionResult:
    status: str
    reasons: list[str] = field(default_factory=list)


def evaluate_completion(state) -> CompletionResult:
    reasons: list[str] = []

    if _get(state, "tracking_required") and not _has_issue(state):
        reasons.append("issue required when tracking_required")

    acceptance = list(_get(state, "acceptance") or [])
    if not acceptance or any(_item_status(item) != "PASS" for item in acceptance):
        reasons.append("acceptance criteria not PASS")

    if _gate(state, "quality_gate") != "PASS":
        reasons.append("quality_gate is not PASS")
    if _gate(state, "security_gate") != "PASS":
        reasons.append("security_gate is not PASS")

    review = _gate(state, "review_gate")
    if review == "SKIP":
        if not _skip_reason(state):
            reasons.append("review_gate SKIP needs skip_reason")
    elif review != "PASS":
        reasons.append("review_gate is not PASS")

    if _confirmed_blocker_or_high(state):
        reasons.append("confirmed blocker/high finding")

    current = _get(state, "current_diff_hash")
    if not _acceptance_evidence_fresh(state, current):
        reasons.append("acceptance evidence is not fresh")

    verified = _get(state, "verified_diff_hash")
    reviewed = _get(state, "reviewed_diff_hash")
    if not (current and current == verified == reviewed):
        reasons.append("verified_diff_hash != current_diff_hash != reviewed_diff_hash")

    if reasons:
        return CompletionResult(status="FAIL", reasons=reasons)
    return CompletionResult(status="READY_TO_SHIP", reasons=[])


def promote_acceptance(state, evidence):
    """Mark a criterion PASS only from existing, fresh, passing evidence."""
    record = _as_evidence(evidence)
    if record is None:
        raise ValueError("evidence does not exist")
    if record.exit_code != 0:
        raise ValueError("evidence exit_code is not 0")
    current = _get(state, "current_diff_hash")
    if record.diff_hash != current:
        raise ValueError("evidence diff_hash does not match current_diff_hash")

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
    return issue is not None and issue != 0


def _gate(state, key):
    value = _get(state, key)
    if value is None:
        return None
    return getattr(value, "gate", value)


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
            summary=str(value.get("summary") or ""),
        )
    return None


def _ledger(state) -> list[Evidence]:
    raw = _get(state, "evidence") or []
    if isinstance(raw, Evidence):
        raw = [raw]
    items = []
    for item in raw:
        record = _as_evidence(item)
        if record is not None:
            items.append(record)
    return items


def _lookup_evidence(state, evidence_id: str | None) -> Evidence | None:
    if not evidence_id:
        return None
    for record in _ledger(state):
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
        return bool(finding.get("confirmed"))
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
