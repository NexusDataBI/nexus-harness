"""Release identity and instrumentation helpers for PostHog observability.

Produces consistent event/error/session metadata without a second SaaS.
Production deploy identity is DeployManifest.digest (``sha256:...``) —
never invent a digest when unavailable.
"""

from __future__ import annotations

from typing import Any

from nexus_harness.posthog import NEVER_CAPTURE_FIELDS

_ALLOWED_ENVIRONMENTS = frozenset({"production", "staging", "development"})
_UNKNOWN = "UNKNOWN"

# Keys that must never appear in release context (reuse PostHog privacy set).
_FORBIDDEN_KEYS = frozenset(
    item.casefold() for item in NEVER_CAPTURE_FIELDS
) | frozenset(
    {
        "email",
        "phone",
        "name",
        "password",
        "authorization",
        "cookie",
        "cookies",
        "api_key",
        "token",
        "secret",
        "personal_api_key",
    }
)


def release_context(
    release: str,
    environment: str,
    project: str,
    *,
    digest: str | None = None,
    route: str | None = None,
    session: str | None = None,
    tenant: str | None = None,
) -> dict[str, Any]:
    """Build standardized release metadata for events/errors/sessions.

    Positional: release SHA, environment, project.
    Optional kwargs: digest (DeployManifest production identity), route/feature,
    session/trace id, pseudonymous tenant/client id.

    Missing ``digest`` is recorded as ``None`` or ``"UNKNOWN"`` — never invented.
    Secrets and unrestricted PII are never included.
    """
    env = str(environment or "").strip()
    if env not in _ALLOWED_ENVIRONMENTS:
        raise ValueError("environment must be one of: production, staging, development")

    deployment_digest: str | None
    if digest is None or str(digest).strip() == "":
        deployment_digest = None
    else:
        deployment_digest = str(digest).strip()

    data: dict[str, Any] = {
        "project": str(project).strip(),
        "environment": env,
        "release": str(release).strip(),
        "deployment_digest": deployment_digest,
    }

    if route is not None and str(route).strip():
        data["route"] = str(route).strip()
    if session is not None and str(session).strip():
        data["session"] = str(session).strip()
    if tenant is not None and str(tenant).strip():
        data["tenant"] = str(tenant).strip()

    for key in data:
        if str(key).casefold() in _FORBIDDEN_KEYS:
            raise ValueError(f"forbidden metadata key: {key}")

    return data
