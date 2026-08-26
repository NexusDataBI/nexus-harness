"""External, per-task operational state (never inside the git worktree)."""

from __future__ import annotations

import os
import re
from pathlib import Path

RUNTIME_HOME_ENV = "NEXUS_RUNTIME_HOME"
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def runtime_home() -> Path:
    raw = os.environ.get(RUNTIME_HOME_ENV)
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".nexus-harness" / "runtime").resolve()


def safe_segment(value: str | None) -> str:
    text = _SAFE.sub("-", str(value or "")).strip(".-")
    if not text or text in {".", ".."}:
        raise ValueError("unsafe identity segment")
    return text[:120]


def task_dir(repo_id: str, task_id: str) -> Path:
    path = runtime_home() / safe_segment(repo_id) / safe_segment(task_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_state_path(repo_id: str, task_id: str) -> Path:
    return task_dir(repo_id, task_id) / "task-state.json"


def default_candidate_path(repo_id: str, task_id: str) -> Path:
    return task_dir(repo_id, task_id) / "memory-candidates.json"


def default_classification_path(repo_id: str, task_id: str) -> Path:
    return task_dir(repo_id, task_id) / "classification.json"


def default_stop_marker(repo_id: str, task_id: str) -> Path:
    return task_dir(repo_id, task_id) / "stop-loop.json"
