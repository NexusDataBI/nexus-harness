"""Path confinement, symlink rejection and git object verification."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_OID_HINT = re.compile(r"^[0-9a-fA-F]{4,40}$|^HEAD$|^[0-9a-fA-F]{40}$")


class PathSafetyError(ValueError):
    """Raised when a filesystem path is unsafe."""


def reject_symlinks(*paths: Path | str) -> None:
    for raw in paths:
        path = Path(raw)
        if path.exists() and path.is_symlink():
            raise PathSafetyError(f"symlink rejected: {path}")


def reject_tree_symlinks(root: Path | str) -> None:
    root = Path(root)
    reject_symlinks(root)
    if not root.exists() or not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in (*dirnames, *filenames):
            reject_symlinks(Path(dirpath) / name)


def confine(path: Path | str, *roots: Path | str) -> Path:
    if not roots:
        raise PathSafetyError("no approved roots")
    candidate = Path(path)
    reject_symlinks(candidate, *roots)
    resolved = candidate.resolve()
    reject_symlinks(resolved)
    for root in roots:
        root_resolved = Path(root).resolve()
        if resolved == root_resolved or resolved.is_relative_to(root_resolved):
            return resolved
    raise PathSafetyError("path escapes approved roots")


def verify_git_oid(repo: Path, value: str) -> str:
    text = str(value or "").strip()
    if not text or text.startswith("-") or ".." in text or "\x00" in text:
        raise ValueError("invalid git object")
    repo = Path(repo)
    reject_symlinks(repo)
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--verify",
            "--quiet",
            "--end-of-options",
            f"{text}^{{commit}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ValueError("invalid git object")
    return completed.stdout.strip()
