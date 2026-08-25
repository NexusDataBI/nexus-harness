from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class InventoryReport:
    file_count: int
    duplicate_file_count: int
    appledouble_count: int
    total_bytes: int
    redundant_bytes: int


def scan_tree(root: Path) -> InventoryReport:
    hashes: dict[str, list[tuple[Path, int]]] = {}
    files = 0
    appledouble = 0
    total_bytes = 0

    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name.startswith("._"):
            appledouble += 1
            continue
        data = path.read_bytes()
        size = len(data)
        digest = sha256(data).hexdigest()
        hashes.setdefault(digest, []).append((path, size))
        files += 1
        total_bytes += size

    duplicate_count = 0
    redundant_bytes = 0
    for group in hashes.values():
        if len(group) > 1:
            duplicate_count += len(group) - 1
            redundant_bytes += sum(size for _, size in group[1:])

    return InventoryReport(
        files,
        duplicate_count,
        appledouble,
        total_bytes,
        redundant_bytes,
    )
