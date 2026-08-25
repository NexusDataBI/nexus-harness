"""Temporary Git repositories for memory freshness tests.

Commands use argv lists only. Never pass shell text.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

_RETAINED_TEMPDIRS: list[tempfile.TemporaryDirectory] = []


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def make_repo_with_changed_file(relative_path: str) -> tuple[Path, str]:
    """Create a tempfile git repo: commit A, change the file, commit B.

    Returns ``(repo_root, base_sha)`` where ``base_sha`` is commit A.
    Identity is configured locally on the repo only.
    """
    tmp = tempfile.TemporaryDirectory(prefix="nexus-memory-git-")
    _RETAINED_TEMPDIRS.append(tmp)
    root = Path(tmp.name)
    _run_git(root, "init", "-b", "main")
    _run_git(root, "config", "user.name", "Nexus Test")
    _run_git(root, "config", "user.email", "nexus-test@example.com")
    _run_git(root, "config", "commit.gpgsign", "false")

    file_path = root / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("commit A contents\n", encoding="utf-8")
    _run_git(root, "add", "--", relative_path)
    _run_git(root, "commit", "-m", "A")
    base_sha = _run_git(root, "rev-parse", "HEAD").stdout.strip()

    file_path.write_text("commit B contents\n", encoding="utf-8")
    _run_git(root, "add", "--", relative_path)
    _run_git(root, "commit", "-m", "B")
    return root, base_sha
