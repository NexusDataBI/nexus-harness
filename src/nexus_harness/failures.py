"""Failure memory: stop unchanged retry loops.

Default no-progress ceiling is 3 (no infinite retry):
  1st identical fingerprint -> retry
  2nd unchanged (same fingerprint, no material diff_hash change) -> diagnose
  3rd+ with no measurable progress -> blocked

A material change in ``diff_hash`` counts as progress: the streak resets
and retry is allowed again (the next record is not immediately blocked).
History is kept in-memory on the ``FailureMemory`` instance.
"""

from dataclasses import dataclass, field
from hashlib import sha256
import re

DEFAULT_CEILING = 3

_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_TEMP_PATH_RE = re.compile(
    r"(?:/private)?(?:/tmp|/var/folders)/[^\s:]+"
    r"|[A-Za-z]:\\(?:Users\\[^\\]+\\AppData\\Local\\Temp|Windows\\Temp)\\[^\s:]+",
    re.IGNORECASE,
)
_HEX_ADDR_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
_PID_TID_RE = re.compile(r"\b(?:pid|tid)[=:\s]+\d+\b", re.IGNORECASE)
_UNIX_TS_RE = re.compile(r"\b1[0-9]{9}(?:[0-9]{3})?\b")


@dataclass
class FailureResult:
    action: str
    fingerprint: str
    attempt: int


@dataclass
class _FingerprintState:
    count: int
    last_diff_hash: str | None


@dataclass
class FailureMemory:
    """Track failure fingerprints and decide retry / diagnose / blocked."""

    ceiling: int = DEFAULT_CEILING
    history: list[str] = field(default_factory=list)
    _states: dict[str, _FingerprintState] = field(default_factory=dict)

    def record(
        self, tool: str, exit_code: int, error: str, *, diff_hash: str | None = None
    ) -> FailureResult:
        fingerprint = fingerprint_failure(tool, exit_code, error)
        self.history.append(fingerprint)
        state = self._states.get(fingerprint)
        if state is None or _material_progress(state.last_diff_hash, diff_hash):
            self._states[fingerprint] = _FingerprintState(
                count=1, last_diff_hash=diff_hash
            )
            return FailureResult(action="retry", fingerprint=fingerprint, attempt=1)

        state.count += 1
        state.last_diff_hash = diff_hash
        return FailureResult(
            action=_action_for(state.count, self.ceiling),
            fingerprint=fingerprint,
            attempt=state.count,
        )

    def to_dict(self) -> dict:
        return {
            "ceiling": self.ceiling,
            "history": list(self.history),
            "states": {
                fingerprint: {
                    "count": state.count,
                    "last_diff_hash": state.last_diff_hash,
                }
                for fingerprint, state in self._states.items()
            },
        }

    @classmethod
    def from_dict(cls, payload: dict | None) -> "FailureMemory":
        payload = payload or {}
        memory = cls(ceiling=int(payload.get("ceiling", DEFAULT_CEILING)))
        memory.history = list(payload.get("history") or [])
        memory._states = {
            fingerprint: _FingerprintState(
                count=int(item.get("count", 0)),
                last_diff_hash=item.get("last_diff_hash"),
            )
            for fingerprint, item in (payload.get("states") or {}).items()
        }
        return memory


def fingerprint_failure(tool: str, exit_code: int, error: str) -> str:
    normalized = normalize_error(error)
    payload = f"{tool}\0{exit_code}\0{normalized}".encode()
    return sha256(payload).hexdigest()


def normalize_error(error: str) -> str:
    text = _TIMESTAMP_RE.sub("<TS>", error)
    text = _TEMP_PATH_RE.sub(_keep_temp_basename, text)
    text = _PID_TID_RE.sub("<PID>", text)
    text = _HEX_ADDR_RE.sub("<HEX>", text)
    text = _UNIX_TS_RE.sub("<TS>", text)
    return " ".join(text.split())


def _keep_temp_basename(match: re.Match[str]) -> str:
    path = match.group(0).rstrip("/\\")
    separator = "\\" if "\\" in path else "/"
    basename = path.rsplit(separator, 1)[-1]
    return f"<TMP>{separator}{basename}"


def _material_progress(previous: str | None, current: str | None) -> bool:
    return (previous or "") != (current or "")


def _action_for(count: int, ceiling: int) -> str:
    if count >= ceiling:
        return "blocked"
    if count >= 2:
        return "diagnose"
    return "retry"
