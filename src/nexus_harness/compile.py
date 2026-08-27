"""Materialize render_all() plus the runtime engine into dist/ and refresh lock hashes."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from nexus_harness.adapters import render_all
from nexus_harness.lockfile import build_lock, write_lock
from nexus_harness.safe import PathSafetyError, reject_symlinks


def compile_harness(root: Path) -> dict:
    root = Path(root).resolve()
    dist = root / "dist"
    reject_symlinks(root)
    if dist.exists():
        reject_symlinks(dist)
    dist.mkdir(parents=True, exist_ok=True)
    for path in sorted(dist.rglob("*"), reverse=True):
        if path.name == ".gitkeep":
            continue
        if path.is_symlink():
            raise PathSafetyError(f"symlink rejected: {path}")
        if path.is_file():
            path.unlink()
        elif path.is_dir() and path != dist:
            try:
                path.rmdir()
            except OSError:
                shutil.rmtree(path)
    for item in render_all(root):
        destination = dist / item.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(item.content)
    package_src = Path(__file__).resolve().parent
    engine_dest = dist / "src" / "nexus_harness"
    if engine_dest.exists():
        shutil.rmtree(engine_dest)
    shutil.copytree(
        package_src,
        engine_dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        symlinks=False,
    )
    core_src = root / "core"
    if core_src.is_dir():
        reject_symlinks(core_src)
        core_dest = dist / "core"
        if core_dest.exists():
            shutil.rmtree(core_dest)
        shutil.copytree(
            core_src,
            core_dest,
            ignore=shutil.ignore_patterns("__pycache__"),
            symlinks=False,
        )
    write_lock(root)
    return build_lock(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile generated runtime files")
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    lock = compile_harness(args.root)
    hashes = lock.get("generated_hashes") or {}
    engine = lock.get("engine_hashes") or {}
    if not hashes:
        raise SystemExit("compile produced empty generated_hashes")
    print(f"compiled {len(hashes)} generated files, {len(engine)} engine files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
