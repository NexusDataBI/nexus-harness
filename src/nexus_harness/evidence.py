from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Evidence:
    id: str
    command: str
    exit_code: int
    diff_hash: str
    summary: str
    artifact: str | None = None
    limitation: str | None = None
    timestamp: str = field(default_factory=_utc_now)

    def is_fresh(self, current_diff_hash: str) -> bool:
        return self.diff_hash == current_diff_hash


def append_evidence(path: Path, evidence: Evidence) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(evidence), ensure_ascii=False) + "\n")


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
            items.append(Evidence(**json.loads(stripped)))
    return items
