"""Runtime-neutral lifecycle hooks.

The runtime adapters only transport JSON.  This module owns policy, state
checkpointing, and the fail-soft memory boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from nexus_harness.completion import evaluate_completion
from nexus_harness.failures import FailureMemory
from nexus_harness.state import TaskState, load_task_state, save_task_state
from nexus_harness.memory import CandidateSignal, MemorySource

try:
    from nexus_harness.memory import (
        checkpoint_memory_candidates,
        collect_memory_candidates,
        consolidate_memory,
        memory_doctor,
        restore_memory_candidates,
        session_recall,
    )
except ImportError:  # pragma: no cover - permits minimal installed runtimes
    checkpoint_memory_candidates = collect_memory_candidates = None
    consolidate_memory = memory_doctor = restore_memory_candidates = session_recall = (
        None
    )


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
    return Path(
        payload.get("project_root")
        or payload.get("repo_root")
        or payload.get("cwd")
        or os.getcwd()
    )


def _state_path(payload: dict) -> Path:
    return Path(
        payload.get("state_path")
        or os.environ.get(
            "NEXUS_STATE_PATH", _root(payload) / ".nexus" / "task-state.json"
        )
    )


def _candidate_path(payload: dict) -> Path:
    return Path(
        payload.get("candidate_path")
        or _root(payload) / ".nexus" / "memory-candidates.json"
    )


def load_current_task(payload: dict | None = None) -> TaskState | dict:
    payload = payload or {}
    if payload.get("task") is not None:
        return payload["task"]
    path = _state_path(payload)
    if not path.exists():
        raise FileNotFoundError(path)
    return load_task_state(path)


def _task(payload: dict) -> TaskState | dict | None:
    try:
        return load_current_task(payload)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


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
    task = _task(payload)
    output: dict[str, Any] = {"warnings": []}
    if task is not None:
        output["task"] = task.to_dict() if hasattr(task, "to_dict") else task
    try:
        restore = bool(
            payload.get("compact")
            or payload.get("resume")
            or payload.get("source") in {"compact", "resume"}
        )
        if restore and restore_memory_candidates is not None:
            candidates = restore_memory_candidates(_candidate_path(payload))
            output["candidate_count"] = len(candidates)
        query = (
            payload.get("query")
            or payload.get("prompt")
            or _value(task, "intent")
            or ""
        )
        if session_recall is not None:
            capsule = session_recall(
                _root(payload),
                project_id=payload.get("project_id") or _value(task, "repo_id"),
                query=query,
                affected_paths=tuple(payload.get("affected_paths", ())),
                portfolio_root=payload.get("portfolio_root"),
                cache_home=payload.get("cache_home"),
                contradictions=tuple(payload.get("contradictions", ())),
            )
            output["capsule"] = capsule.text if hasattr(capsule, "text") else capsule
        else:
            output["capsule"] = ""
    except Exception as exc:
        output["capsule"] = ""
        output["warnings"].append({"code": "memory_unavailable", "message": str(exc)})
    return HookResult(0, output)


def user_prompt_submit(payload: dict) -> HookResult:
    query = payload.get("query") or payload.get("prompt") or ""
    previous = payload.get("previous_classification")
    current = payload.get("classification") or {
        "query": query,
        "affected_paths": sorted(payload.get("affected_paths", ())),
        "domain": payload.get("domain"),
    }
    if previous == current:
        return HookResult(0, {"refreshed": False})
    result = session_start({**payload, "query": query})
    return HookResult(result.exit_code, {**(result.output or {}), "refreshed": True})


def policy_gate(payload: dict) -> HookResult:
    if payload.get("deny") is True:
        return HookResult(2, {"denied": True})
    return HookResult(0, {"allowed": True})


def failure_memory(payload: dict) -> HookResult:
    task = _task(payload)
    memory = _value(task, "failures") if task is not None else None
    if not isinstance(memory, FailureMemory):
        memory = FailureMemory.from_dict(memory if isinstance(memory, dict) else None)
    result = memory.record(
        str(payload.get("tool", "unknown")),
        int(payload.get("exit_code", 1)),
        str(payload.get("error", "")),
        diff_hash=payload.get("diff_hash"),
    )
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
    task = _task(payload)
    if task is None:
        return HookResult(0, {"checkpointed": False})
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
    marker = _root(payload) / ".nexus" / "stop-loop.json"
    identity = str(identity_value)
    try:
        previous = (
            json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        )
        if not isinstance(previous, dict):
            raise TypeError("corrupt stop marker")
        timestamp = float(previous.get("timestamp", 0))
        if previous.get("identity") == identity and time.time() - timestamp < 60:
            return HookResult(0, {"loop_protected": True, "identity": identity})
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({"identity": identity, "timestamp": time.time()}),
            encoding="utf-8",
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return completion_gate(payload)


def task_completed(payload: dict) -> HookResult:
    gate = completion_gate(payload)
    if gate.exit_code != 0:
        return gate
    if collect_memory_candidates is None or consolidate_memory is None:
        return HookResult(0, {**(gate.output or {}), "memory": "unavailable"})
    task = _task(payload) or {}
    signals = _as_signals(payload.get("signals", ()))
    candidates = _as_drafts(payload.get("candidates", ()))
    if not candidates:
        candidates = collect_memory_candidates(
            project_id=payload.get("project_id") or _value(task, "repo_id", ""),
            task_id=payload.get("task_id") or _value(task, "task_id", ""),
            signals=signals,
        )
    try:
        committed = payload.get("current_commit") or payload.get("base_commit")
        if not committed:
            return HookResult(
                0,
                {
                    **(gate.output or {}),
                    "memory": "not consolidated: missing base_commit",
                },
            )
        records = consolidate_memory(
            _root(payload),
            candidates,
            current_commit=committed,
            evidence_lookup=payload.get("evidence_lookup"),
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
