"""Restricted client-VM deploy contract — allowlisted service + digest only.

Production identity is an immutable ``sha256:`` digest. The client-VM entrypoint
(``infra/client-vm/nexus-deploy``) must never eval user strings; this module
parses argv and orchestrates pull/recreate/health/rollback with injectable
runners for tests (no Docker daemon required).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Mapping, Sequence

SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# Registry repository path only — no tag (:) and no digest (@).
IMAGE_REPO_RE = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+$"
)
# Reject shell metacharacters / control chars in any argv token.
_META_RE = re.compile(r"[;|&$`<>(){}[\]\\\"'*?~\n\r\t ]")

DEFAULT_SERVICES_PATH = Path(
    os.environ.get("NEXUS_DEPLOY_SERVICES", "/etc/nexus-deploy/services.json")
)
DEFAULT_EVIDENCE_PATH = Path(
    os.environ.get(
        "NEXUS_DEPLOY_EVIDENCE",
        "/var/lib/nexus-deploy/last-rollback.json",
    )
)

ComposeRunner = Callable[[Sequence[str]], int]
HealthChecker = Callable[[str], bool]


class DeployError(ValueError):
    """Invalid deploy request (argv, allowlist, or digest)."""


@dataclass(frozen=True)
class DeployRequest:
    action: str
    service: str
    digest: str


@dataclass(frozen=True)
class DeployResult:
    ok: bool
    status: str  # PASS | ROLLBACK | ERROR
    service: str
    digest: str
    previous_digest: str | None = None
    message: str = ""


def _reject_metacharacters(token: str, *, label: str) -> None:
    if not token:
        raise DeployError(f"empty {label}")
    if _META_RE.search(token) or any(ord(ch) < 32 for ch in token):
        raise DeployError(f"{label} contains forbidden characters")


def _load_services_mapping(
    services: Mapping | None, services_path: Path | None
) -> dict:
    if services is not None:
        raw = dict(services)
    else:
        path = services_path or DEFAULT_SERVICES_PATH
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeployError(f"cannot load services allowlist: {exc}") from exc
    if not isinstance(raw, dict):
        raise DeployError("services allowlist must be a JSON object")
    entries = raw.get("services")
    if not isinstance(entries, dict) or not entries:
        raise DeployError("services allowlist missing non-empty 'services' map")
    return entries


def parse_deploy_argv(
    argv: Sequence[str],
    *,
    services: Mapping | None = None,
    services_path: Path | None = None,
) -> DeployRequest:
    """Parse ``deploy <service> <sha256:digest>`` — never shell-eval argv."""
    if len(argv) != 3:
        raise DeployError(
            "usage: nexus-deploy deploy <service> <sha256:digest> "
            "(exactly three arguments)"
        )

    action, service, digest = (str(argv[0]), str(argv[1]), str(argv[2]))
    for label, token in (("action", action), ("service", service), ("digest", digest)):
        _reject_metacharacters(token, label=label)

    if action != "deploy":
        raise DeployError(f"unsupported action {action!r}; only 'deploy' is allowed")

    if not SERVICE_RE.fullmatch(service):
        raise DeployError(f"service must match {SERVICE_RE.pattern}; got {service!r}")

    if digest == "latest" or digest.lower() == "latest":
        raise DeployError("mutable tag 'latest' cannot be production identity")
    if not DIGEST_RE.fullmatch(digest):
        raise DeployError(
            f"digest must match sha256:<64 hex lowercase>; got {digest!r}"
        )

    allowlist = _load_services_mapping(services, services_path)
    if service not in allowlist:
        raise DeployError(f"unknown service {service!r} (not in allowlist)")
    entry = allowlist[service]
    if not isinstance(entry, dict):
        raise DeployError(f"allowlist entry for {service!r} must be an object")
    _validate_allowlist_image(str(entry.get("image") or ""))

    return DeployRequest(action=action, service=service, digest=digest)


def _validate_allowlist_image(image: str) -> None:
    """Require an untagged registry repository path (same idea as deploy-manifest)."""
    image = str(image).strip()
    if not image:
        raise DeployError("allowlist entry missing image (untagged repository path)")
    _reject_metacharacters(image, label="image")
    if ":" in image or "@" in image:
        raise DeployError(
            "image must be an untagged registry path (no tag, no @digest, no latest)"
        )
    if image.lower() == "latest" or not IMAGE_REPO_RE.fullmatch(image):
        raise DeployError(f"image must be a repository path without tag; got {image!r}")


def resolve_argv(
    argv: Sequence[str],
    *,
    ssh_original_command: str | None = None,
) -> list[str]:
    """Build deploy argv from process argv or SSH forced-command original.

    With ``authorized_keys command=/usr/local/bin/nexus-deploy``, OpenSSH runs
    the forced command with an empty argv and places the client-supplied remote
    command in ``SSH_ORIGINAL_COMMAND``. We split on whitespace only (no shell,
    no ``shlex`` quote expansion) and still validate every token later.
    """
    args = [str(a) for a in argv]
    if len(args) == 3:
        return args
    if len(args) == 0 and ssh_original_command:
        raw = str(ssh_original_command).strip()
        if not raw:
            raise DeployError("empty SSH_ORIGINAL_COMMAND")
        # No shell — reject quotes/escapes and shell metacharacters in the raw string.
        if any(ch in raw for ch in "\\\"'`"):
            raise DeployError("SSH_ORIGINAL_COMMAND contains forbidden quote/escape")
        if re.search(r"[;|&$<>(){}[\]*?~\n\r\t]", raw):
            raise DeployError("SSH_ORIGINAL_COMMAND contains forbidden characters")
        parts = raw.split()
        if len(parts) != 3:
            raise DeployError(
                "SSH_ORIGINAL_COMMAND must be exactly: deploy <service> <digest>"
            )
        return parts
    raise DeployError(
        "usage: nexus-deploy deploy <service> <sha256:digest> "
        "(or SSH_ORIGINAL_COMMAND with the same three tokens)"
    )


def _read_digest_var(env_file: Path, var_name: str) -> str | None:
    if not env_file.is_file():
        return None
    prefix = f"{var_name}="
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip().strip('"').strip("'")
    return None


def _write_digest_var(env_file: Path, var_name: str, digest: str) -> None:
    _reject_metacharacters(var_name, label="digest_var")
    if not DIGEST_RE.fullmatch(digest):
        raise DeployError(f"refusing to write non-digest value for {var_name}")
    lines: list[str] = []
    found = False
    prefix = f"{var_name}="
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(prefix):
                lines.append(f"{var_name}={digest}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{var_name}={digest}")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _default_compose_runner(argv: Sequence[str]) -> int:
    # Fixed binary + argv list — never assemble a shell string.
    cmd = ["docker", "compose", *argv]
    completed = subprocess.run(cmd, check=False)  # noqa: S603
    return int(completed.returncode)


def _default_health_checker(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            return 200 <= int(getattr(resp, "status", 0) or 0) < 300
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False


def _assert_compose_binds_digest(compose_file: Path, digest_var: str) -> None:
    """Fail closed: compose must reference digest_var and must not use :latest.

    String scan only (stdlib) — no YAML parser.
    """
    try:
        text = compose_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeployError(f"cannot read compose_file: {exc}") from exc
    if ":latest" in text:
        raise DeployError(
            "compose_file must not contain :latest (bind image to digest env var)"
        )
    if digest_var not in text:
        raise DeployError(
            f"compose_file must reference digest_var {digest_var!r} "
            "(image must be bound to the digest env)"
        )


def _compose_base(entry: Mapping) -> list[str]:
    compose_file = str(entry.get("compose_file") or "")
    project_dir = str(entry.get("project_dir") or "")
    env_file = str(entry.get("env_file") or "")
    if not compose_file:
        raise DeployError("allowlist entry missing compose_file")
    if not env_file:
        raise DeployError("allowlist entry missing env_file")
    _reject_metacharacters(compose_file, label="compose_file")
    _reject_metacharacters(env_file, label="env_file")
    base: list[str] = []
    if project_dir:
        _reject_metacharacters(project_dir, label="project_dir")
        base.extend(["--project-directory", project_dir])
    # Bind digest env so compose resolves image@${DIGEST_VAR} from this file.
    base.extend(["--env-file", env_file, "-f", compose_file])
    return base


def _pull_and_recreate(
    *,
    service: str,
    entry: Mapping,
    compose_runner: ComposeRunner,
) -> None:
    base = _compose_base(entry)
    # Pull by service (compose resolves digest from env); recreate only that service.
    rc = compose_runner([*base, "pull", service])
    if rc != 0:
        raise DeployError(f"compose pull failed for {service} (rc={rc})")
    rc = compose_runner([*base, "up", "-d", "--force-recreate", "--no-deps", service])
    if rc != 0:
        raise DeployError(f"compose up failed for {service} (rc={rc})")


def _write_evidence(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _restore_previous_digest(
    *,
    service: str,
    entry: Mapping,
    env_file: Path,
    digest_var: str,
    previous: str,
    compose_runner: ComposeRunner,
    health_checker: HealthChecker,
    health_url: str,
) -> bool:
    """Restore previous digest, recreate service, re-check health.

    Returns whether health succeeded after restore. If recreate fails, still
    returns False (caller must write evidence with health_restored=false).
    """
    _write_digest_var(env_file, digest_var, previous)
    try:
        _pull_and_recreate(service=service, entry=entry, compose_runner=compose_runner)
    except DeployError:
        return False
    return bool(health_checker(health_url))


def run_deploy(
    argv: Sequence[str],
    *,
    services_path: Path | None = None,
    services: Mapping | None = None,
    compose_runner: ComposeRunner | None = None,
    health_checker: HealthChecker | None = None,
    evidence_path: Path | None = None,
) -> DeployResult:
    """Execute allowlisted deploy with health gate and digest rollback."""
    compose_runner = compose_runner or _default_compose_runner
    health_checker = health_checker or _default_health_checker
    evidence_path = Path(evidence_path) if evidence_path else DEFAULT_EVIDENCE_PATH

    allowlist = _load_services_mapping(services, services_path)
    req = parse_deploy_argv(argv, services={"services": allowlist})
    entry = allowlist[req.service]

    digest_var = str(entry.get("digest_var") or "")
    if not digest_var or not re.fullmatch(r"^[A-Z][A-Z0-9_]*$", digest_var):
        raise DeployError(f"invalid digest_var in allowlist for {req.service}")
    env_file = Path(str(entry.get("env_file") or ""))
    if not env_file.parts:
        raise DeployError(f"allowlist entry for {req.service} missing env_file")
    health_url = str(entry.get("health_url") or "")
    if not health_url.startswith(("http://", "https://")):
        raise DeployError(
            f"allowlist entry for {req.service} missing http(s) health_url"
        )
    # Allow : / . - _ in URL; reject shell metacharacters.
    if re.search(r"[;|&$`<>(){}\\\"'*?\n\r\t ]", health_url):
        raise DeployError("health_url contains forbidden characters")

    compose_path = Path(str(entry.get("compose_file") or ""))
    previous = _read_digest_var(env_file, digest_var)
    digest_written = False

    def _rollback_evidence(health_after: bool, *, message: str) -> DeployResult:
        payload = {
            "status": "ROLLBACK",
            "service": req.service,
            "attempted_digest": req.digest,
            "restored_digest": previous,
            "health_restored": bool(health_after),
        }
        _write_evidence(evidence_path, payload)
        return DeployResult(
            ok=False,
            status="ROLLBACK",
            service=req.service,
            digest=req.digest,
            previous_digest=previous,
            message=message,
        )

    try:
        _assert_compose_binds_digest(compose_path, digest_var)
        _write_digest_var(env_file, digest_var, req.digest)
        digest_written = True
        _pull_and_recreate(
            service=req.service, entry=entry, compose_runner=compose_runner
        )
        if not health_checker(health_url):
            # Health is part of the gate — compose rc=0 alone is not PASS.
            health_after = False
            if previous and DIGEST_RE.fullmatch(previous):
                health_after = _restore_previous_digest(
                    service=req.service,
                    entry=entry,
                    env_file=env_file,
                    digest_var=digest_var,
                    previous=previous,
                    compose_runner=compose_runner,
                    health_checker=health_checker,
                    health_url=health_url,
                )
            return _rollback_evidence(
                health_after,
                message="health check failed; previous digest restored",
            )
        return DeployResult(
            ok=True,
            status="PASS",
            service=req.service,
            digest=req.digest,
            previous_digest=previous,
            message="deploy healthy",
        )
    except DeployError as exc:
        # After env write, pull/up failure must still restore previous digest.
        if digest_written and previous and DIGEST_RE.fullmatch(previous):
            health_after = _restore_previous_digest(
                service=req.service,
                entry=entry,
                env_file=env_file,
                digest_var=digest_var,
                previous=previous,
                compose_runner=compose_runner,
                health_checker=health_checker,
                health_url=health_url,
            )
            return _rollback_evidence(
                health_after,
                message=f"{exc}; previous digest restored",
            )
        if digest_written:
            # No valid previous digest — still record that deploy failed mid-flight.
            payload = {
                "status": "ROLLBACK",
                "service": req.service,
                "attempted_digest": req.digest,
                "restored_digest": previous,
                "health_restored": False,
            }
            _write_evidence(evidence_path, payload)
        return DeployResult(
            ok=False,
            status="ERROR",
            service=req.service,
            digest=req.digest,
            previous_digest=previous,
            message=str(exc),
        )


def main(argv: Sequence[str] | None = None) -> int:
    import sys

    raw_args = list(sys.argv[1:] if argv is None else argv)
    services_path = Path(
        os.environ.get("NEXUS_DEPLOY_SERVICES", str(DEFAULT_SERVICES_PATH))
    )
    evidence_path = Path(
        os.environ.get("NEXUS_DEPLOY_EVIDENCE", str(DEFAULT_EVIDENCE_PATH))
    )
    try:
        args = resolve_argv(
            raw_args,
            ssh_original_command=os.environ.get("SSH_ORIGINAL_COMMAND"),
        )
        result = run_deploy(
            args,
            services_path=services_path,
            evidence_path=evidence_path,
        )
    except DeployError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if result.ok:
        print(f"PASS: {result.service}@{result.digest}")
        return 0
    print(f"{result.status}: {result.message}", file=sys.stderr)
    return 1 if result.status == "ROLLBACK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
