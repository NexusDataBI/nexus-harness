"""Reproducible local release candidate for Nexus Harness v4.

``scripts/build`` is the assembler. ``nexus build`` compiles adapters only.
Unit tests inject precondition hooks and must never recurse unittest discover.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from nexus_harness.compile import compile_harness

RELEASE_SCHEMA = "nexus-harness-release/v1"
RELEASE_VERSION = "4.0.0"
RELEASE_CHANNEL = "GA"
BUNDLE_NAME = "nexus-harness-v4"
ARCHIVE_NAME = "nexus-harness-v4.tar.gz"
HEX_HASH = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
ALLOWED_DEBT = frozenset({"resolved", "accepted_residual"})
INCLUDE_TREES = (
    "core",
    "skills",
    "profiles",
    "src",
    "scripts",
    "docs",
    "evals",
    "dist",
    "upstream",
    "tests",
    "templates",
    "adapters",
    "agents",
    "hooks",
    "ci",
    "infra",
)
INCLUDE_ROOT_FILES = (
    "harness.lock",
    "README.md",
    "projects.toml",
    ".gitignore",
)
EXCLUDE_DIR_NAMES = frozenset(
    {
        ".git",
        ".worktrees",
        ".superpowers",
        ".nexus",
        "__pycache__",
        ".venv",
        "venv",
        "legacy",
        "inputs",
        "screenshots",
        "traces",
        "htmlcov",
        "client-data",
        "secrets",
        ".coverage",
        "egg-info",
    }
)
EXCLUDE_FILE_NAMES = frozenset(
    {
        ".DS_Store",
        ".env",
        "credentials.json",
        "id_rsa",
        "id_ed25519",
        ".coverage",
    }
)
SECRET_NAMES = frozenset(
    {
        ".env",
        "credentials.json",
        "id_rsa",
        "id_ed25519",
        "github.token",
        "posthog.secret",
    }
)
SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"phx_[A-Za-z0-9]{20,}"),
    re.compile(r"POSTHOG_PERSONAL_API_KEY\s*=\s*\S+"),
    re.compile(
        r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----\s+[A-Za-z0-9+/]{40,}"
    ),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)
TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".toml",
    ".json",
    ".py",
    ".sh",
    ".yml",
    ".yaml",
    ".env",
    ".lock",
    ".cfg",
    ".ini",
    ".pem",
    ".key",
}


class ReleaseError(Exception):
    """Raised when a release precondition fails or assembly cannot proceed."""


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class ReleaseChecks:
    """Optional hooks. ``None`` runs the default implementation."""

    validate: Callable[[Path], CheckResult] | None = None
    tests: Callable[[Path], CheckResult] | None = None
    evals: Callable[[Path], CheckResult] | None = None
    golden: Callable[[Path], CheckResult] | None = None
    drift: Callable[[Path], CheckResult] | None = None
    acceptance: Callable[[Path], CheckResult] | None = None
    debt: Callable[[Path], CheckResult] | None = None
    migration: Callable[[Path], CheckResult] | None = None
    upstream: Callable[[Path], CheckResult] | None = None
    secrets: Callable[[Path], CheckResult] | None = None


def render_rc_identity(manifest: Mapping[str, object]) -> str:
    """Sidecar generated from MANIFEST.json. Never hand-copied into git docs."""
    files = manifest.get("files") or []
    count = len(files) if isinstance(files, list) else 0
    return (
        "# Nexus Harness packaged release identity\n\n"
        "Generated from `release/MANIFEST.json`. Do not edit by hand.\n\n"
        f"- schema: `{manifest.get('schema')}`\n"
        f"- version: `{manifest.get('version')}`\n"
        f"- channel: `{manifest.get('channel')}`\n"
        f"- Final RC source commit: `{manifest.get('commit')}`\n"
        f"- Final RC lock identity: `{manifest.get('lock_identity')}`\n"
        f"- Final RC logical manifest count: {count}\n"
    )


_STALE_RC_TOKENS = (
    "d8fd36091792a585d741eddb264ca4d61382c94c",
    "08d8ff2bee0902a00cb8620abf588d866cf199cfb7ce70c9389d78df23b68112",
    "files in logical manifest: 794",
)
_CLAIM_COMMIT = re.compile(r"Final RC source commit:\s*`([0-9a-f]{40})`", re.IGNORECASE)
_CLAIM_LOCK = re.compile(r"Final RC lock identity:\s*`([0-9a-f]{64})`", re.IGNORECASE)
_CLAIM_FILES = re.compile(
    r"Final RC logical manifest count:\s*`?(\d+)`?", re.IGNORECASE
)


def acceptance_manifest_drift(
    text: str, manifest: Mapping[str, object] | None = None
) -> tuple[str, ...]:
    """Detect stale or contradictory packaged-release claims in acceptance docs."""
    errors: list[str] = []
    for token in _STALE_RC_TOKENS:
        if token in text:
            errors.append(f"stale packaged identity: {token}")
    if "Engineering verification HEAD" not in text:
        errors.append("missing Engineering verification HEAD label")
    if "release/MANIFEST.json" not in text:
        errors.append("acceptance doc does not reference MANIFEST.json")
    if manifest is not None:
        commit = str(manifest.get("commit") or "")
        lock = str(manifest.get("lock_identity") or "")
        files = manifest.get("files") or []
        count = len(files) if isinstance(files, list) else 0
        found_commit = _CLAIM_COMMIT.search(text)
        if found_commit and found_commit.group(1) != commit:
            errors.append("Final RC source commit disagrees with MANIFEST.json")
        found_lock = _CLAIM_LOCK.search(text)
        if found_lock and found_lock.group(1) != lock:
            errors.append("Final RC lock identity disagrees with MANIFEST.json")
        found_files = _CLAIM_FILES.search(text)
        if found_files and int(found_files.group(1)) != count:
            errors.append(
                "Final RC logical manifest count disagrees with MANIFEST.json"
            )
    return tuple(errors)


def logical_manifest(manifest: dict) -> dict:
    """Compare release identity without gzip timestamp bytes."""
    files = [
        {
            "path": item["path"],
            "sha256": item["sha256"],
            "size": item["size"],
        }
        for item in manifest.get("files") or []
    ]
    return {
        "schema": manifest.get("schema"),
        "version": manifest.get("version"),
        "channel": manifest.get("channel"),
        "commit": manifest.get("commit"),
        "lock_identity": manifest.get("lock_identity"),
        "files": files,
    }


def default_check_validate(root: Path) -> CheckResult:
    from nexus_harness.validate import validate_repository

    result = validate_repository(root)
    if result.errors:
        return CheckResult("validate", False, "; ".join(result.errors))
    return CheckResult("validate", True, "scripts/validate PASS")


def default_check_tests(root: Path) -> CheckResult:
    if os.environ.get("_NEXUS_RELEASE_UNITTEST_ACTIVE") == "1":
        raise ReleaseError(
            "refusing to recurse unittest discover from inside unittest; "
            "inject checks.tests"
        )
    env = os.environ.copy()
    src = str(Path(root) / "src")
    env["PYTHONPATH"] = src + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    detail = ((completed.stderr or "") + (completed.stdout or "")).strip()
    if completed.returncode != 0:
        return CheckResult("tests", False, detail[-4000:] or "unittest suite failed")
    return CheckResult("tests", True, "unittest suite PASS")


def default_check_evals(root: Path) -> CheckResult:
    from nexus_harness.evals import run_evals

    cases = Path(root) / "evals" / "cases"
    if not cases.is_dir():
        return CheckResult("evals", False, "evals cases directory missing")
    report = run_evals(cases, repo_root=root)
    if report.gate != "PASS":
        return CheckResult("evals", False, report.summary)
    return CheckResult("evals", True, report.summary)


def default_check_golden(root: Path) -> CheckResult:
    from nexus_harness.adapters import render_all

    golden = Path(root) / "tests" / "golden"
    if not golden.is_dir():
        return CheckResult("golden", True, "no golden snapshots; skipped")
    rendered = {item.relative_path: item.content for item in render_all(root)}
    expected = {
        path.relative_to(golden).as_posix(): path.read_bytes()
        for path in golden.rglob("*")
        if path.is_file()
        and path.name != ".DS_Store"
        and path.suffix not in {".pyc", ".pyo"}
        and "__pycache__" not in path.parts
    }
    if set(rendered) != set(expected):
        return CheckResult("golden", False, "runtime golden file set differs")
    for relative, payload in expected.items():
        if rendered.get(relative) != payload:
            return CheckResult("golden", False, f"runtime golden drift: {relative}")
    return CheckResult("golden", True, f"{len(expected)} golden files match")


def default_check_drift(root: Path) -> CheckResult:
    from nexus_harness.lockfile import (
        build_lock,
        expected_engine_hashes,
        expected_generated_hashes,
        on_disk_engine_hashes,
        on_disk_generated_hashes,
    )

    lock_path = Path(root) / "harness.lock"
    if not lock_path.is_file():
        return CheckResult("drift", False, "missing harness.lock")
    try:
        recorded = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult("drift", False, f"unparseable harness.lock: {exc}")
    current = build_lock(root)
    errors: list[str] = []
    if recorded.get("canonical_hashes") != current["canonical_hashes"]:
        errors.append("canonical hash drift vs harness.lock")
    expected = expected_generated_hashes(root)
    if recorded.get("generated_hashes") != expected:
        errors.append("generated hash drift vs harness.lock")
    else:
        on_disk = on_disk_generated_hashes(root)
        if on_disk and on_disk != expected:
            errors.append("generated hash drift vs harness.lock")
    expected_engine = expected_engine_hashes(root)
    if recorded.get("engine_hashes") != expected_engine:
        errors.append("engine hash drift vs harness.lock")
    else:
        on_disk_engine = on_disk_engine_hashes(root)
        if on_disk_engine and on_disk_engine != expected_engine:
            errors.append("engine hash drift vs harness.lock")
    if recorded.get("adapter_versions") != current["adapter_versions"]:
        errors.append("adapter version drift vs harness.lock")
    if errors:
        return CheckResult("drift", False, "; ".join(errors))
    return CheckResult("drift", True, "no generated drift")


def default_check_acceptance(root: Path) -> CheckResult:
    matrix = Path(root) / "tests" / "test_acceptance_matrix.py"
    sidecar = Path(root) / "docs" / "release" / "v4-acceptance.md"
    if not matrix.is_file() and not sidecar.is_file():
        return CheckResult("acceptance", True, "no acceptance matrix; skipped")
    if matrix.is_file() and "INCOMPLETE" in matrix.read_text(encoding="utf-8"):
        return CheckResult("acceptance", False, "acceptance incomplete")
    return CheckResult("acceptance", True, "acceptance matrix present")


def default_check_debt(root: Path) -> CheckResult:
    path = Path(root) / "docs" / "migration" / "debt.json"
    if not path.is_file():
        return CheckResult("debt", False, "missing docs/migration/debt.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult("debt", False, f"unparseable debt.json: {exc}")
    unresolved = [
        str(item.get("id") or "?")
        for item in (payload.get("items") or [])
        if str(item.get("status") or "") not in ALLOWED_DEBT
    ]
    if unresolved:
        return CheckResult(
            "debt",
            False,
            "unresolved Plan 8 debt: " + ", ".join(unresolved),
        )
    return CheckResult("debt", True, "debt resolved or accepted residual")


def default_check_migration(root: Path) -> CheckResult:
    from nexus_harness.migration_report import _unresolved_divergent

    ledger_path = Path(root) / "docs" / "migration" / "skill-ledger.json"
    heuristics_path = Path(root) / "docs" / "migration" / "unique-heuristics.md"
    if not ledger_path.is_file() or not heuristics_path.is_file():
        return CheckResult("migration", False, "migration decision files missing")
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult("migration", False, f"unparseable skill-ledger: {exc}")
    if not isinstance(ledger, list):
        return CheckResult("migration", False, "skill-ledger must be a JSON array")
    text = heuristics_path.read_text(encoding="utf-8")
    count = _unresolved_divergent(ledger, text)
    if count:
        return CheckResult(
            "migration", False, f"unresolved migration decisions: {count}"
        )
    return CheckResult("migration", True, "migration decisions resolved")


def default_check_upstream(root: Path) -> CheckResult:
    lock_path = Path(root) / "upstream" / "vendor-lock.json"
    if not lock_path.is_file():
        return CheckResult("upstream", False, "missing upstream/vendor-lock.json")
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult("upstream", False, f"unparseable vendor-lock: {exc}")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return CheckResult("upstream", False, "upstream lock missing sources")
    errors: list[str] = []
    for source in sources:
        identity = str(source.get("id", "?"))
        revision = str(source.get("revision", ""))
        if not HEX_HASH.fullmatch(revision):
            errors.append(f"upstream lock revision is not a hash: {identity}")
        canonical = source.get("canonical_path")
        if not isinstance(canonical, str) or not canonical:
            errors.append(f"upstream lock missing canonical_path: {identity}")
        elif not (Path(root) / canonical).exists():
            errors.append(f"upstream lock canonical_path missing: {canonical}")
    if errors:
        return CheckResult("upstream", False, "; ".join(errors))
    return CheckResult("upstream", True, f"{len(sources)} upstream sources locked")


_SECRET_SCAN_SKIP_PREFIXES = ("tests/", "evals/")
_FAKE_SECRET = re.compile(
    r"(?i)should_never|supersecret|example|placeholder|do_not_leak|your-key|changeme"
)
_PLACEHOLDER_ASSIGNMENT = re.compile(
    r"""(?i)POSTHOG_PERSONAL_API_KEY\s*=\s*["']?(?:\$\{?\w+\}?|\.\.\.|<[^>]+>|your-\S+|TODO|none|null)"""
)


def _secret_hit_is_fixture(text: str, match: re.Match[str]) -> bool:
    snippet = match.group(0)
    if _FAKE_SECRET.search(snippet):
        return True
    if snippet.upper().startswith("POSTHOG_PERSONAL_API_KEY"):
        return bool(_PLACEHOLDER_ASSIGNMENT.search(snippet))
    return False


def default_check_secrets(root: Path) -> CheckResult:
    hits: list[str] = []
    for path in _iter_release_source_files(root):
        relative = path.relative_to(root).as_posix()
        if relative.startswith(_SECRET_SCAN_SKIP_PREFIXES):
            continue
        if path.name in SECRET_NAMES or path.name.endswith(".token"):
            hits.append(relative)
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name not in INCLUDE_ROOT_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match and not _secret_hit_is_fixture(text, match):
                hits.append(relative)
                break
    if hits:
        return CheckResult(
            "secrets", False, "secret scan failed: " + ", ".join(hits[:12])
        )
    return CheckResult("secrets", True, "secret scan clean")


_DEFAULTS: tuple[tuple[str, Callable[[Path], CheckResult]], ...] = (
    ("validate", default_check_validate),
    ("tests", default_check_tests),
    ("evals", default_check_evals),
    ("golden", default_check_golden),
    ("drift", default_check_drift),
    ("acceptance", default_check_acceptance),
    ("debt", default_check_debt),
    ("migration", default_check_migration),
    ("upstream", default_check_upstream),
    ("secrets", default_check_secrets),
)


def _run_preconditions(root: Path, checks: ReleaseChecks) -> None:
    failures: list[str] = []
    for name, default in _DEFAULTS:
        hook = getattr(checks, name) or default
        result = hook(root)
        if not result.ok:
            failures.append(f"{result.name}: {result.message}")
    if failures:
        raise ReleaseError("release preconditions failed: " + "; ".join(failures))


def _excluded(relative: str, path: Path) -> bool:
    parts = Path(relative).parts
    if relative == "release" or relative.startswith("release/"):
        return True
    if any(part in EXCLUDE_DIR_NAMES for part in parts):
        return True
    if any(part.endswith(".egg-info") for part in parts):
        return True
    if any(part.startswith("._") for part in parts):
        return True
    if path.name in EXCLUDE_FILE_NAMES or path.name.startswith("._"):
        return True
    if path.suffix in {".pyc", ".pyo"} or path.name.endswith(".bak"):
        return True
    if path.name == ".gitkeep" and "dist" not in parts:
        return True
    if relative.startswith("adapters/dist/"):
        return True
    return False


def _iter_release_source_files(root: Path):
    root = Path(root)
    for tree in INCLUDE_TREES:
        base = root / tree
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if not _excluded(relative, path):
                yield path
    for name in INCLUDE_ROOT_FILES:
        path = root / name
        if path.is_file() and not path.is_symlink() and not _excluded(name, path):
            yield path


def _dist_needs_compile(root: Path) -> bool:
    dist = Path(root) / "dist"
    if not dist.is_dir():
        return True
    for path in dist.rglob("*"):
        if path.is_file() and path.name != ".gitkeep" and not path.is_symlink():
            if "__pycache__" in path.parts:
                continue
            return False
    return True


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    commit = (completed.stdout or "").strip()
    if completed.returncode != 0 or not commit:
        raise ReleaseError("source commit missing; git HEAD unavailable")
    return commit


def _copy_filtered(source: Path, destination: Path, *, prefix: str) -> None:
    for path in source.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source).as_posix()
        tagged = f"{prefix}/{relative}" if prefix else relative
        if _excluded(tagged, path):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _assemble(root: Path, bundle: Path) -> None:
    for tree in INCLUDE_TREES:
        source = root / tree
        if source.is_dir():
            _copy_filtered(source, bundle / tree, prefix=tree)
    for name in INCLUDE_ROOT_FILES:
        source = root / name
        if source.is_file() and not source.is_symlink():
            shutil.copyfile(source, bundle / name)


def _install_text(commit: str, lock_identity: str) -> str:
    return (
        f"# Nexus Harness {RELEASE_VERSION}\n\n"
        f"GA ({RELEASE_CHANNEL}) — stable 4.0.0.\n\n"
        f"- schema: `{RELEASE_SCHEMA}`\n"
        f"- source commit: `{commit}`\n"
        f"- lock identity: `{lock_identity}`\n\n"
        "## Verify\n\n"
        "```bash\n"
        f"tar -xzf {ARCHIVE_NAME}\n"
        f"cd {BUNDLE_NAME}\n"
        "PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'\n"
        "scripts/validate\n"
        "```\n\n"
        "## Compile and install\n\n"
        "`scripts/build` assembled this archive. "
        "`nexus build` / `scripts/compile` materializes adapters into `dist/`.\n\n"
        "```bash\n"
        "scripts/compile\n"
        "scripts/install dist /path/to/runtime\n"
        "```\n\n"
        "Do not overwrite `~/.claude`, `~/.cursor` or `~/.codex` without backup.\n"
        "Do not treat missing VPS / GitHub Project / PostHog activation as a "
        "local-release failure.\n"
    )


def _hash_bundle(bundle: Path) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for path in sorted(bundle.rglob("*")):
        if not path.is_file():
            continue
        relative = f"{BUNDLE_NAME}/{path.relative_to(bundle).as_posix()}"
        data = path.read_bytes()
        items.append(
            {
                "path": relative,
                "sha256": sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    return items


def _normalize_tarinfo(
    info: tarfile.TarInfo, *, directory: bool, executable: bool
) -> tarfile.TarInfo:
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o755 if directory or executable else 0o644
    return info


def _write_archive(bundle: Path, archive: Path) -> None:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        root_info = tarfile.TarInfo(BUNDLE_NAME)
        root_info.type = tarfile.DIRTYPE
        tar.addfile(_normalize_tarinfo(root_info, directory=True, executable=True))
        entries = sorted(
            bundle.rglob("*"),
            key=lambda path: path.relative_to(bundle).as_posix(),
        )
        for path in entries:
            name = f"{BUNDLE_NAME}/{path.relative_to(bundle).as_posix()}"
            info = tar.gettarinfo(str(path), arcname=name)
            executable = bool(path.stat().st_mode & 0o111)
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                tar.addfile(_normalize_tarinfo(info, directory=True, executable=True))
            elif path.is_file():
                info = _normalize_tarinfo(info, directory=False, executable=executable)
                with path.open("rb") as handle:
                    tar.addfile(info, handle)
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(tar_buf.getvalue())


def build_release(
    root: Path,
    *,
    checks: ReleaseChecks | None = None,
    source_commit: str | None = None,
    compile_adapters: bool = True,
    output_root: Path | None = None,
) -> dict:
    root = Path(root)
    _run_preconditions(root, checks or ReleaseChecks())
    if compile_adapters and _dist_needs_compile(root):
        compile_harness(root)
    commit = source_commit or _git_head(root)
    release_root = Path(output_root) if output_root else root / "release"
    bundle = release_root / BUNDLE_NAME
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    _assemble(root, bundle)
    lock_path = bundle / "harness.lock"
    if not lock_path.is_file():
        raise ReleaseError("lockfile missing from release bundle")
    lock_identity = sha256(lock_path.read_bytes()).hexdigest()
    (bundle / "INSTALL.md").write_text(
        _install_text(commit, lock_identity),
        encoding="utf-8",
    )
    files = _hash_bundle(bundle)
    manifest = {
        "schema": RELEASE_SCHEMA,
        "version": RELEASE_VERSION,
        "channel": RELEASE_CHANNEL,
        "commit": commit,
        "lock_identity": lock_identity,
        "files": files,
    }
    release_root.mkdir(parents=True, exist_ok=True)
    (release_root / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (release_root / "RC-IDENTITY.md").write_text(
        render_rc_identity(manifest),
        encoding="utf-8",
    )
    _write_archive(bundle, release_root / ARCHIVE_NAME)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a reproducible Nexus harness release candidate"
    )
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    parser.add_argument(
        "--skip-compile",
        action="store_true",
        help="do not compile adapters even if dist/ is only .gitkeep",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        manifest = build_release(
            args.root,
            compile_adapters=not args.skip_compile,
        )
    except ReleaseError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"wrote {manifest['version']} ({manifest['channel']}) → release/{ARCHIVE_NAME}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
