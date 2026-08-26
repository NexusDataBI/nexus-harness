"""Build affected Docker images once and capture immutable digests."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Callable, Sequence

from nexus_harness.deploy_manifest import DeployManifest, assemble_deploy_manifest


Runner = Callable[..., tuple[int, str, str]]

# Dockerfile / build-context defaults for known SDR-style services.
# Unknown services fall back to apps/<service>/Dockerfile at repo root.
_DOCKERFILE_DEFAULTS: dict[str, tuple[str, str]] = {
    "web": ("apps/web/Dockerfile", "."),
    "server": ("apps/server/Dockerfile", "."),
    "figma-worker": ("apps/server/Dockerfile.figma-worker", "."),
}


@dataclass(frozen=True)
class ImageBuildPlan:
    """Deterministic BuildKit plan for one affected image."""

    service: str
    image: str
    human_tag: str
    dockerfile: str
    context: str
    cache_ref: str
    metadata_file: str
    build_argv: tuple[str, ...]


def image_ref_for(
    repository: str,
    service: str,
    *,
    registry: str = "ghcr.io",
) -> str:
    """Map owner/repo + service to a deterministic GHCR repository path."""
    owner, _, repo = str(repository).partition("/")
    if not owner or not repo:
        raise ValueError(f"repository must be owner/name, got {repository!r}")
    if not service or not str(service).strip():
        raise ValueError("service must be non-empty")
    return f"{registry}/{owner.lower()}/{repo.lower()}-{service.strip()}"


def _dockerfile_for(service: str) -> tuple[str, str]:
    return _DOCKERFILE_DEFAULTS.get(service, (f"apps/{service}/Dockerfile", "."))


def _metadata_path_for(service: str, *, project_root: Path | None = None) -> str:
    """Deterministic BuildKit metadata path for one service (no TOCTOU inspect)."""
    base = Path(project_root) if project_root is not None else Path(".")
    return str(base / ".nexus" / "build-metadata" / f"{service}.json")


def _buildkit_argv(
    *,
    image: str,
    human_tag: str,
    dockerfile: str,
    context: str,
    cache_ref: str,
    metadata_file: str,
) -> tuple[str, ...]:
    tagged = f"{image}:{human_tag}"
    cache_from = f"type=registry,ref={cache_ref}"
    cache_to = f"type=registry,ref={cache_ref},mode=max"
    return (
        "docker",
        "buildx",
        "build",
        f"--cache-from={cache_from}",
        f"--cache-to={cache_to}",
        f"--file={dockerfile}",
        f"--tag={tagged}",
        f"--metadata-file={metadata_file}",
        "--push",
        context,
    )


def plan_image_builds(
    images: Sequence[str],
    *,
    repository: str,
    commit: str,
    registry: str = "ghcr.io",
    project_root: Path | None = None,
) -> tuple[ImageBuildPlan, ...]:
    """Generate BuildKit commands for each *affected* image only."""
    if not commit or not str(commit).strip():
        raise ValueError("commit (git SHA) is required for human tags")
    human_tag = str(commit).strip()
    plans: list[ImageBuildPlan] = []
    seen: set[str] = set()
    for service in images:
        name = str(service).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        image = image_ref_for(repository, name, registry=registry)
        dockerfile, context = _dockerfile_for(name)
        cache_ref = f"{image}:buildcache"
        metadata_file = _metadata_path_for(name, project_root=project_root)
        argv = _buildkit_argv(
            image=image,
            human_tag=human_tag,
            dockerfile=dockerfile,
            context=context,
            cache_ref=cache_ref,
            metadata_file=metadata_file,
        )
        plans.append(
            ImageBuildPlan(
                service=name,
                image=image,
                human_tag=human_tag,
                dockerfile=dockerfile,
                context=context,
                cache_ref=cache_ref,
                metadata_file=metadata_file,
                build_argv=argv,
            )
        )
    return tuple(plans)


def _default_runner(
    argv: Sequence[str], *, cwd: Path | None = None
) -> tuple[int, str, str]:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _normalize_digest(raw: str) -> str:
    text = (raw or "").strip().splitlines()
    if not text:
        raise ValueError("empty digest from build metadata")
    digest = text[0].strip().strip('"').strip("'")
    if digest.startswith("sha256:") and len(digest) == len("sha256:") + 64:
        return digest
    raise ValueError(f"invalid build metadata digest: {digest!r}")


def _digest_from_metadata_file(path: Path) -> str:
    """Read ``containerimage.digest`` written by BuildKit ``--metadata-file``."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable build metadata at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"build metadata must be a JSON object at {path}")
    raw = payload.get("containerimage.digest")
    if raw is None or not str(raw).strip():
        raise ValueError(f"build metadata missing containerimage.digest at {path}")
    return _normalize_digest(str(raw))


def build_affected_images(
    images: Sequence[str],
    *,
    repository: str,
    commit: str,
    registry: str = "ghcr.io",
    project_root: Path | None = None,
    runner: Runner | None = None,
) -> dict:
    """Build/push affected images once and emit an immutable deploy manifest.

    Production identity is the BuildKit ``containerimage.digest`` captured from
    ``--metadata-file`` at build time — not a follow-up inspect of a mutable
    ``image:<commit>`` tag (TOCTOU). The git SHA tag remains for human
    discoverability only. ``runner`` is injectable so tests never touch the
    network or a real registry.
    """
    run = runner or _default_runner
    cwd = project_root
    plans = plan_image_builds(
        images,
        repository=repository,
        commit=commit,
        registry=registry,
        project_root=project_root,
    )
    artifacts: list[DeployManifest] = []
    for plan in plans:
        meta_path = Path(plan.metadata_file)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        code, _stdout, stderr = run(plan.build_argv, cwd=cwd)
        if code != 0:
            raise RuntimeError(
                f"build/push failed for {plan.service} (exit {code}): {stderr}"
            )
        digest = _digest_from_metadata_file(meta_path)
        artifacts.append(
            DeployManifest(service=plan.service, image=plan.image, digest=digest)
        )
    return assemble_deploy_manifest(
        repository=repository,
        commit=commit,
        artifacts=tuple(artifacts),
    )
