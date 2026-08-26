"""Runtime-neutral lifecycle hooks.

The runtime adapters only transport JSON.  This module owns policy, state
checkpointing, and the fail-soft memory boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from nexus_harness.completion import evaluate_completion
from nexus_harness.failures import FailureMemory
from nexus_harness.pretool import evaluate_pretool
from nexus_harness.runtime_home import (
    default_candidate_path,
    default_classification_path,
    default_state_path,
    default_stop_marker,
    runtime_home,
)
from nexus_harness.safe import PathSafetyError, confine, reject_symlinks, verify_git_oid
from nexus_harness.state import TaskState, load_task_state, save_task_state
from nexus_harness.memory import CandidateSignal, MemorySource

try:
    from nexus_harness.memory import (
        checkpoint_memory_candidates,
        collect_memory_candidates,
        consolidate_memory,
        memory_doctor,
        parse_contradictions,
        restore_memory_candidates,
        session_recall,
    )
except ImportError:  # pragma: no cover - permits minimal installed runtimes
    checkpoint_memory_candidates = collect_memory_candidates = None
    consolidate_memory = memory_doctor = restore_memory_candidates = session_recall = (
        None
    )
    parse_contradictions = None


@dataclass(frozen=True)
class HookResult:
    exit_code: int = 0
    output: dict[str, Any] | None = None


def _value(value: Any, key: str, default: Any = None) -> Any:
    return (
        value.get(key, default)
        if isinstance(value, dict)
        else getattr(value, key, default)
    )


def _root(payload: dict) -> Path:
    raw = (
        payload.get("project_root")
        or payload.get("repo_root")
        or payload.get("cwd")
        or os.getcwd()
    )
    path = Path(raw)
    reject_symlinks(path)
    return path.resolve()


def _identities(payload: dict) -> tuple[str | None, str | None]:
    task = payload.get("task")
    repo_id = (
        payload.get("repo_id") or payload.get("project_id") or _value(task, "repo_id")
    )
    task_id = payload.get("task_id") or _value(task, "task_id")
    return (
        str(repo_id) if repo_id else None,
        str(task_id) if task_id else None,
    )


def _approved_runtime_root() -> Path:
    return runtime_home()


def _confine_runtime_path(path: Path) -> Path:
    return confine(path, _approved_runtime_root())


def _state_path(payload: dict) -> Path:
    if payload.get("state_path"):
        return _confine_runtime_path(Path(payload["state_path"]))
    repo_id, task_id = _identities(payload)
    if repo_id and task_id:
        return default_state_path(repo_id, task_id)
    raise FileNotFoundError("task state identity missing")


def _candidate_path(payload: dict) -> Path:
    if payload.get("candidate_path"):
        return _confine_runtime_path(Path(payload["candidate_path"]))
    repo_id, task_id = _identities(payload)
    if repo_id and task_id:
        return default_candidate_path(repo_id, task_id)
    raise FileNotFoundError("candidate identity missing")


class TaskStateStatus(str):
    OK = "ok"
    ABSENT = "absent"
    CORRUPT = "corrupt"


def load_current_task(payload: dict | None = None) -> TaskState | dict:
    payload = payload or {}
    if payload.get("task") is not None:
        task = payload["task"]
        if isinstance(task, dict):
            try:
                return TaskState.from_dict(task) if "task_id" in task else task
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("corrupt task state") from exc
        return task
    path = _state_path(payload)
    if not path.exists():
        raise FileNotFoundError(path)
    reject_symlinks(path)
    return load_task_state(path)


def _inspect_task(payload: dict) -> tuple[str, TaskState | dict | None]:
    try:
        return TaskStateStatus.OK, load_current_task(payload)
    except FileNotFoundError:
        return TaskStateStatus.ABSENT, None
    except PathSafetyError:
        return TaskStateStatus.CORRUPT, None
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return TaskStateStatus.CORRUPT, None


def _task(payload: dict) -> TaskState | dict | None:
    status, task = _inspect_task(payload)
    if status != TaskStateStatus.OK:
        return None
    return task


def _as_drafts(items: list | tuple) -> list:
    if restore_memory_candidates is None:
        return list(items)
    # Objects are already public MemoryDrafts; JSON dictionaries are accepted
    # for stdin-driven hooks.
    try:
        from nexus_harness.memory import MemoryDraft

        return [
            MemoryDraft.from_json_dict(item) if isinstance(item, dict) else item
            for item in items
        ]
    except (ImportError, KeyError, TypeError, ValueError):
        return list(items)


def _as_signals(items: list | tuple) -> tuple[CandidateSignal, ...]:
    signals = []
    for item in items:
        if isinstance(item, CandidateSignal):
            signals.append(item)
            continue
        if not isinstance(item, dict):
            continue
        try:
            sources = tuple(
                source
                if isinstance(source, MemorySource)
                else MemorySource(str(source["kind"]), str(source["ref"]))
                for source in item.get("sources", ())
            )
            signals.append(
                CandidateSignal(
                    kind=str(item["kind"]),
                    title=str(item["title"]),
                    statement=str(item["statement"]),
                    sources=sources,
                    evidence_ids=tuple(map(str, item.get("evidence_ids", ()))),
                    related_paths=tuple(map(str, item.get("related_paths", ()))),
                    tags=tuple(map(str, item.get("tags", ()))),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(signals)


def completion_gate(payload: dict | None = None) -> HookResult:
    payload = payload or {}
    task = _task(payload)
    if task is None:
        return HookResult(2, {"status": "FAIL", "reasons": ["task state unavailable"]})
    explicit = _value(task, "completion_status")
    if explicit == "FAIL":
        reasons = _value(task, "completion_reasons")
        if not reasons:
            reasons = _value(task, "reasons", [])
        return HookResult(2, {"status": "FAIL", "reasons": list(reasons)})
    result = evaluate_completion(task)
    reasons = list(result.reasons)
    if result.status == "FAIL":
        for reason in _value(task, "completion_reasons", ()) or _value(
            task, "reasons", ()
        ):
            if reason not in reasons:
                reasons.append(reason)
    return HookResult(
        0 if result.status == "READY_TO_SHIP" else 2,
        {"status": result.status, "reasons": reasons},
    )


def session_start(payload: dict) -> HookResult:
    status, task = _inspect_task(payload)
    output: dict[str, Any] = {
        "warnings": [],
        "task_state": status,
        "memory": "absent",
    }
    compact = bool(
        payload.get("compact")
        or payload.get("resume")
        or payload.get("source") in {"compact", "resume"}
    )
    if status == TaskStateStatus.CORRUPT:
        output["warnings"].append(
            {"code": "task_state_corrupt", "message": "task state is corrupt"}
        )
        return HookResult(2, output)
    if compact and status == TaskStateStatus.ABSENT:
        output["warnings"].append(
            {"code": "task_state_absent", "message": "task state is required"}
        )
        return HookResult(2, output)
    if task is not None:
        output["task"] = task.to_dict() if hasattr(task, "to_dict") else task
    try:
        if compact and restore_memory_candidates is not None:
            candidates = restore_memory_candidates(_candidate_path(payload))
            output["candidate_count"] = len(candidates)
        query = (
            payload.get("query")
            or payload.get("prompt")
            or _value(task, "intent")
            or ""
        )
        if parse_contradictions is None:
            contradictions, contradiction_findings = (), []
        else:
            contradictions, contradiction_findings = parse_contradictions(
                payload.get("contradictions", ())
            )
        output["warnings"].extend(contradiction_findings)
        if session_recall is not None:
            capsule = session_recall(
                _root(payload),
                project_id=payload.get("project_id") or _value(task, "repo_id"),
                query=query,
                affected_paths=tuple(payload.get("affected_paths", ())),
                portfolio_root=payload.get("portfolio_root"),
                cache_home=payload.get("cache_home"),
                contradictions=contradictions,
            )
            output["capsule"] = capsule.text if hasattr(capsule, "text") else capsule
            output["memory"] = "ok" if output["capsule"] else "absent"
            if getattr(capsule, "findings", ()):
                output["warnings"].extend(list(capsule.findings))
        else:
            output["capsule"] = ""
            output["memory"] = "unavailable"
    except FileNotFoundError:
        output["capsule"] = ""
        output["memory"] = "absent"
    except Exception as exc:
        output["capsule"] = ""
        output["memory"] = "unavailable"
        output["warnings"].append({"code": "memory_unavailable", "message": str(exc)})
    return HookResult(0, output)


def _classification_payload(payload: dict) -> dict:
    query = payload.get("query") or payload.get("prompt") or ""
    return payload.get("classification") or {
        "query": query,
        "affected_paths": sorted(payload.get("affected_paths", ())),
        "domain": payload.get("domain"),
    }


def _classification_digest(payload: dict) -> str:
    encoded = json.dumps(_classification_payload(payload), sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def user_prompt_submit(payload: dict) -> HookResult:
    query = payload.get("query") or payload.get("prompt") or ""
    digest = _classification_digest(payload)
    repo_id, task_id = _identities(payload)
    if repo_id and task_id:
        path = default_classification_path(repo_id, task_id)
        if path.is_file():
            previous = path.read_text(encoding="utf-8").strip()
            if previous == digest:
                return HookResult(0, {"refreshed": False})
        path.write_text(digest + "\n", encoding="utf-8")
    elif payload.get("previous_classification") == _classification_payload(payload):
        return HookResult(0, {"refreshed": False})
    result = session_start({**payload, "query": query})
    return HookResult(result.exit_code, {**(result.output or {}), "refreshed": True})


def policy_gate(payload: dict) -> HookResult:
    code, output = evaluate_pretool(payload)
    return HookResult(code, output)


def failure_memory(payload: dict) -> HookResult:
    status, task = _inspect_task(payload)
    if status == TaskStateStatus.CORRUPT:
        return HookResult(2, {"status": "FAIL", "reasons": ["task state corrupt"]})
    if task is None:
        task = TaskState.new(
            str(payload.get("task_id") or "unknown"),
            str(payload.get("repo_id") or payload.get("project_id") or "unknown"),
        )
    memory = _value(task, "failures")
    if not isinstance(memory, FailureMemory):
        memory = FailureMemory.from_dict(memory if isinstance(memory, dict) else None)
    result = memory.record(
        str(payload.get("tool") or payload.get("tool_name") or "unknown"),
        int(payload.get("exit_code", 1)),
        str(payload.get("error", "")),
        diff_hash=payload.get("diff_hash"),
    )
    if hasattr(task, "failures"):
        task.failures = memory
    elif isinstance(task, dict):
        task["failures"] = memory.to_dict()
        task = TaskState.from_dict(task) if "task_id" in task else task
    try:
        save_task_state(task, _state_path(payload))
    except (FileNotFoundError, PathSafetyError, OSError, ValueError):
        return HookResult(2, {"status": "FAIL", "reasons": ["failure memory persist"]})
    return HookResult(
        0,
        {
            "action": result.action,
            "fingerprint": result.fingerprint,
            "attempt": result.attempt,
        },
    )


def batch_maintenance(payload: dict) -> HookResult:
    return HookResult(0, {"maintained": True, "count": payload.get("count", 0)})


def checkpoint(payload: dict) -> HookResult:
    status, task = _inspect_task(payload)
    if status != TaskStateStatus.OK or task is None:
        return HookResult(
            2,
            {
                "checkpointed": False,
                "task_state": status,
                "status": "FAIL",
                "reasons": ["task state unavailable"],
            },
        )
    if isinstance(task, dict):
        task = TaskState.from_dict(task)
    save_task_state(task, _state_path(payload))
    candidates = _as_drafts(payload.get("candidates", ()))
    if checkpoint_memory_candidates is not None:
        checkpoint_memory_candidates(_candidate_path(payload), candidates)
    return HookResult(0, {"checkpointed": True, "candidate_count": len(candidates)})


def compact_observation(payload: dict) -> HookResult:
    return checkpoint(payload)


def post_compact_observer(payload: dict) -> HookResult:
    del payload
    return HookResult(0, {"observed": True, "restored": False})


def config_drift(payload: dict) -> HookResult:
    return HookResult(0, {"drift": bool(payload.get("drift", False))})


def _stop_marker_path(payload: dict) -> Path:
    repo_id, task_id = _identities(payload)
    if repo_id and task_id:
        return default_stop_marker(repo_id, task_id)
    return runtime_home() / "stop" / "unscoped.json"


def stop_handler(payload: dict) -> HookResult:
    """Prevent repeated Stop delivery from recursively re-entering the gate."""
    identity_value = next(
        (
            payload.get(key)
            for key in ("session_id", "transcript_path", "event_id")
            if payload.get(key)
        ),
        None,
    )
    if identity_value is None:
        return completion_gate(payload)
    marker = _stop_marker_path(payload)
    identity = str(identity_value)
    try:
        previous = (
            json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        )
        if not isinstance(previous, dict):
            raise TypeError("corrupt stop marker")
        timestamp = float(previous.get("timestamp", 0))
        if previous.get("identity") == identity and time.time() - timestamp < 60:
            exit_code = int(previous.get("exit_code", 2))
            output = dict(previous.get("output") or {})
            output["loop_protected"] = True
            output["identity"] = identity
            return HookResult(exit_code, output)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        previous = {}
    result = completion_gate(payload)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "identity": identity,
                    "timestamp": time.time(),
                    "exit_code": result.exit_code,
                    "output": result.output,
                },
                default=str,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    return result


def _authoritative_signals(task) -> tuple[CandidateSignal, ...]:
    signals: list[CandidateSignal] = []
    for item in _value(task, "evidence") or []:
        record = item if isinstance(item, dict) else None
        if record is None:
            evidence_id = getattr(item, "id", None)
            exit_code = getattr(item, "exit_code", 1)
            summary = getattr(item, "summary", "")
        else:
            evidence_id = record.get("id")
            exit_code = record.get("exit_code", 1)
            summary = record.get("summary") or ""
        if not evidence_id:
            continue
        try:
            if int(exit_code) != 0:
                continue
        except (TypeError, ValueError):
            continue
        signals.append(
            CandidateSignal(
                kind="invariant",
                title=f"Evidence {evidence_id}",
                statement=str(summary) or f"Recorded evidence {evidence_id}",
                sources=(MemorySource("deterministic_evidence", str(evidence_id)),),
                evidence_ids=(str(evidence_id),),
            )
        )
    review = _value(task, "review_gate")
    if review == "PASS":
        signals.append(
            CandidateSignal(
                kind="confirmed_bug_lesson",
                title="Review passed",
                statement="Review gate passed for the current verified diff.",
                sources=(MemorySource("review_finding", "review_gate"),),
            )
        )
    for finding in _value(task, "findings") or []:
        if not isinstance(finding, dict):
            continue
        if str(finding.get("status") or "").lower() != "confirmed":
            continue
        kind = str(finding.get("kind") or finding.get("type") or "").lower()
        if kind != "incident":
            continue
        identity = str(finding.get("id") or "incident")
        signals.append(
            CandidateSignal(
                kind="confirmed_incident",
                title=identity,
                statement=str(
                    finding.get("summary") or finding.get("message") or identity
                ),
                sources=(MemorySource("incident", identity),),
            )
        )
    return tuple(signals)


def _evidence_lookup(task):
    table: dict[str, object] = {}
    for item in _value(task, "evidence") or []:
        if isinstance(item, dict) and item.get("id"):
            table[str(item["id"])] = item
        elif hasattr(item, "id"):
            table[str(item.id)] = item

    def lookup(evidence_id: str):
        return table.get(str(evidence_id))

    return lookup


def task_completed(payload: dict) -> HookResult:
    status, task = _inspect_task(payload)
    if status == TaskStateStatus.CORRUPT:
        return HookResult(2, {"status": "FAIL", "reasons": ["task state corrupt"]})
    payload_tid = payload.get("task_id")
    loaded_tid = _value(task, "task_id") if task is not None else None
    if payload_tid and loaded_tid and str(payload_tid) != str(loaded_tid):
        return HookResult(2, {"status": "FAIL", "reasons": ["task_id mismatch"]})
    gate = completion_gate(payload)
    if gate.exit_code != 0:
        return gate
    if collect_memory_candidates is None or consolidate_memory is None:
        return HookResult(0, {**(gate.output or {}), "memory": "unavailable"})
    task = task or {}
    signals = _authoritative_signals(task)
    candidates = collect_memory_candidates(
        project_id=payload.get("project_id") or _value(task, "repo_id", ""),
        task_id=_value(task, "task_id", "") or payload.get("task_id") or "",
        signals=signals,
    )
    try:
        committed = verify_git_oid(_root(payload), "HEAD")
        records = consolidate_memory(
            _root(payload),
            candidates,
            current_commit=committed,
            evidence_lookup=_evidence_lookup(task),
        )
        return HookResult(0, {**(gate.output or {}), "consolidated": len(records)})
    except Exception as exc:
        return HookResult(0, {**(gate.output or {}), "memory_warning": str(exc)})


def session_end(payload: dict) -> HookResult:
    result = checkpoint(payload) if payload.get("candidates") else HookResult(0, {})
    output = dict(result.output or {})
    if memory_doctor is not None:
        try:
            report = memory_doctor(_root(payload), payload.get("portfolio_root"))
            output["memory_health"] = _value(report, "gate")
        except Exception as exc:
            output["memory_health"] = "UNAVAILABLE"
            output.setdefault("warnings", []).append(
                {"code": "memory_doctor", "message": str(exc)}
            )
    return HookResult(result.exit_code, output)


_HANDLERS = {
    "SessionStart": session_start,
    "UserPromptSubmit": user_prompt_submit,
    "PreToolUse": policy_gate,
    "PostToolUseFailure": failure_memory,
    "PostToolBatch": batch_maintenance,
    "TaskCompleted": task_completed,
    "Stop": stop_handler,
    "PreCompact": compact_observation,
    "PostCompact": post_compact_observer,
    "ConfigChange": config_drift,
    "SessionEnd": session_end,
}


def dispatch(
    event: str, payload: dict | None = None, *, completion_gate: bool = False
) -> HookResult:
    payload = payload or {}
    if event == "TaskCompleted" or completion_gate:
        return (
            task_completed(payload)
            if event == "TaskCompleted"
            else globals()["completion_gate"](payload)
        )
    handler = _HANDLERS.get(event)
    return handler(payload) if handler else HookResult(0, {"ignored_event": event})


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("event", nargs="?")
    parser.add_argument("--event", dest="event_option")
    args = parser.parse_args(argv)
    event = args.event_option or args.event
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {}
    result = dispatch(event, payload, completion_gate=event == "TaskCompleted")
    if result.output:
        print(json.dumps(result.output, default=str))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
