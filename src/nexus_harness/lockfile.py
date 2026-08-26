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


def _digest_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _skip_generated_file(path: Path) -> bool:
    return (
        "__pycache__" in path.parts
        or path.suffix in {".pyc", ".pyo"}
        or path.name == ".DS_Store"
        or path.name == ".gitkeep"
    )


def _tree_hashes(root: Path, directory: str) -> dict[str, str]:
    tree = root / directory
    if not tree.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): _digest(path)
        for path in sorted(tree.rglob("*"))
        if path.is_file() and not _skip_generated_file(path)
    }


def expected_generated_hashes(root: Path) -> dict[str, str]:
    """Hash generated artifacts from canonical sources — not from ignored dist/.

    Matches what ``compile_harness`` materializes: render_all() adapters, the
    Python engine copy, and a snapshot of ``core/``.
    """
    from nexus_harness.adapters import render_all

    root = Path(root)
    hashes: dict[str, str] = {}
    for item in render_all(root):
        hashes[f"dist/{item.relative_path}"] = _digest_bytes(item.content)

    package_src = Path(__file__).resolve().parent
    for path in sorted(package_src.rglob("*")):
        if not path.is_file() or _skip_generated_file(path):
            continue
        rel = path.relative_to(package_src).as_posix()
        hashes[f"dist/src/nexus_harness/{rel}"] = _digest(path)

    core_src = root / "core"
    if core_src.is_dir():
        for path in sorted(core_src.rglob("*")):
            if not path.is_file() or _skip_generated_file(path):
                continue
            rel = path.relative_to(core_src).as_posix()
            hashes[f"dist/core/{rel}"] = _digest(path)

    return dict(sorted(hashes.items()))


def on_disk_generated_hashes(root: Path) -> dict[str, str]:
    """Hashes of materialized dist/ files, excluding .gitkeep."""
    return {
        path: digest
        for path, digest in _tree_hashes(root, "dist").items()
        if Path(path).name != ".gitkeep"
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

    return {
        "schema_version": 1,
        "canonical_hashes": dict(sorted(canonical_hashes.items())),
        "generated_hashes": expected_generated_hashes(root),
        "adapter_versions": dict(sorted(ADAPTER_VERSIONS.items())),
    }


def serialize_lock(lock: Mapping[str, object]) -> str:
    return json.dumps(lock, indent=2, sort_keys=True) + "\n"


def write_lock(root: Path, destination: Path | None = None) -> Path:
    output = destination or root / "harness.lock"
    output.write_text(serialize_lock(build_lock(root)), encoding="utf-8")
    return output


def serialize_lock(lock: Mapping[str, object]) -> str:
    return json.dumps(lock, indent=2, sort_keys=True) + "\n"


def write_lock(root: Path, destination: Path | None = None) -> Path:
    output = destination or root / "harness.lock"
    output.write_text(serialize_lock(build_lock(root)), encoding="utf-8")
    return output
