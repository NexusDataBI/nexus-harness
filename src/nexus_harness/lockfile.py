import json
from hashlib import sha256
from pathlib import Path
from typing import Mapping


ADAPTER_VERSIONS = {
    "claude": 1,
    "cursor": 1,
    "codex": 1,
}


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _tree_hashes(root: Path, directory: str) -> dict[str, str]:
    tree = root / directory
    if not tree.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): _digest(path)
        for path in sorted(tree.rglob("*"))
        if (
            path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
            and path.name != ".DS_Store"
        )
    }


def build_lock(root: Path) -> dict[str, object]:
    canonical_hashes = {
        **_tree_hashes(root, "core"),
        **_tree_hashes(root, "skills"),
        **_tree_hashes(root, "profiles"),
    }
    upstream_lock = root / "upstream" / "vendor-lock.json"
    if upstream_lock.is_file():
        canonical_hashes[upstream_lock.relative_to(root).as_posix()] = _digest(
            upstream_lock
        )

    generated_hashes = {
        path: digest
        for path, digest in _tree_hashes(root, "dist").items()
        if Path(path).name != ".gitkeep"
    }

    return {
        "schema_version": 1,
        "canonical_hashes": dict(sorted(canonical_hashes.items())),
        "generated_hashes": dict(sorted(generated_hashes.items())),
        "adapter_versions": dict(sorted(ADAPTER_VERSIONS.items())),
    }


def serialize_lock(lock: Mapping[str, object]) -> str:
    return json.dumps(lock, indent=2, sort_keys=True) + "\n"


def write_lock(root: Path, destination: Path | None = None) -> Path:
    output = destination or root / "harness.lock"
    output.write_text(serialize_lock(build_lock(root)), encoding="utf-8")
    return output
