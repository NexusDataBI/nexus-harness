from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Evidence:
    id: str
    command: str
    exit_code: int
    diff_hash: str
    base_commit: str
    summary: str
    artifact: str | None = None
    limitation: str | None = None
    timestamp: str = field(default_factory=_utc_now)

    def is_fresh(self, current_diff_hash: str) -> bool:
        return self.diff_hash == current_diff_hash


def append_evidence(path: Path, evidence: Evidence) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    records = [asdict(item) for item in read_evidence(destination)]
    records.append(asdict(evidence))
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def read_evidence(path: Path) -> list[Evidence]:
    source = Path(path)
    if not source.exists():
        return []
    items = []
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                items.append(Evidence(**json.loads(stripped)))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
    return items
