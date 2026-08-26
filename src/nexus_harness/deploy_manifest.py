"""Immutable deploy manifest — production identity is digest, never latest."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MUTABLE_TAGS = frozenset(
    {
        "latest",
        "main",
        "master",
        "dev",
        "devel",
        "development",
        "prod",
        "production",
        "staging",
        "stage",
        "stable",
        "edge",
        "nightly",
        "canary",
        "buildcache",
    }
)


def _image_tag(image: str) -> str | None:
    """Return the tag portion of a registry reference, if present.

    Digests in the image field (``@sha256:...``) are treated as tags for
    rejection — production identity belongs in the digest field only.
    """
    if "@" in image:
        return image.rsplit("@", 1)[1]
    # Tag sits after the last colon that follows the final slash (or start).
    slash = image.rfind("/")
    colon = image.rfind(":")
    if colon > slash:
        return image[colon + 1 :]
    return None


def _validate_production_identity(image: str, digest: str) -> None:
    if not digest or not str(digest).strip():
        raise ValueError("deploy digest must be a non-empty sha256 digest")
    digest = str(digest).strip()
    if digest == "latest" or digest.lower() in _MUTABLE_TAGS:
        raise ValueError(f"mutable tag {digest!r} cannot be production identity")
    if not _DIGEST_RE.match(digest):
        raise ValueError(f"deploy digest must match sha256:<64 hex>, got {digest!r}")

    image = str(image).strip()
    if not image:
        raise ValueError("deploy image must be a non-empty registry path")
    tag = _image_tag(image)
    if tag is not None:
        tag_lower = tag.lower()
        if tag_lower == "latest" or tag_lower in _MUTABLE_TAGS:
            raise ValueError(f"mutable tag {tag!r} cannot be production identity")
        if tag_lower.startswith("sha256:"):
            raise ValueError(
                "image must not embed digest; put sha256 identity in digest field"
            )
        # Any other tag on the image field is also mutable identity — reject.
        raise ValueError(f"image must be an untagged registry path; got tag {tag!r}")


@dataclass(frozen=True)
class DeployManifest:
    """One immutable deploy artifact.

    Production identity is ``digest`` (``sha256:...``). ``image`` is the
    registry repository path without a tag. Human SHA tags may exist on the
    registry for discoverability; they are not the deploy identity.
    """

    service: str
    image: str
    digest: str

    def __post_init__(self) -> None:
        if not self.service or not str(self.service).strip():
            raise ValueError("deploy service must be non-empty")
        _validate_production_identity(self.image, self.digest)

    def to_dict(self) -> dict[str, str]:
        return {
            "service": self.service,
            "image": self.image,
            "digest": self.digest,
        }


def assemble_deploy_manifest(
    *,
    repository: str,
    commit: str,
    artifacts: Sequence[DeployManifest],
) -> dict:
    """Bind repository + commit + validated artifacts into a deploy document."""
    if not repository or not str(repository).strip():
        raise ValueError("repository must be non-empty")
    if not commit or not str(commit).strip():
        raise ValueError("commit must be non-empty")
    return {
        "repository": str(repository).strip(),
        "commit": str(commit).strip(),
        "artifacts": [artifact.to_dict() for artifact in artifacts],
    }


def load_deploy_manifest(document: Mapping[str, object]) -> dict:
    """Validate and normalize a deploy manifest mapping."""
    repository = str(document.get("repository") or "").strip()
    commit = str(document.get("commit") or "").strip()
    raw_artifacts = document.get("artifacts") or ()
    if not isinstance(raw_artifacts, Sequence) or isinstance(
        raw_artifacts, (str, bytes)
    ):
        raise ValueError("artifacts must be a list")
    artifacts: list[DeployManifest] = []
    for item in raw_artifacts:
        if not isinstance(item, Mapping):
            raise ValueError("each artifact must be an object")
        artifacts.append(
            DeployManifest(
                service=str(item.get("service") or ""),
                image=str(item.get("image") or ""),
                digest=str(item.get("digest") or ""),
            )
        )
    return assemble_deploy_manifest(
        repository=repository,
        commit=commit,
        artifacts=tuple(artifacts),
    )
