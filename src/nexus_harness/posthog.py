"""Safe PostHog Cloud configuration and HTTP boundary.

This module is the ONLY PostHog HTTP/config boundary. Incident policy,
GitHub governance, and postdeploy verification must not parse raw HTTP
responses. Secrets never enter Git, PROJECT.md, memory, logs, or
exception strings.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from nexus_harness.config import load_toml

_LOG = logging.getLogger(__name__)

_CORE = Path(__file__).resolve().parents[2] / "core" / "observability"
DEFAULT_CONFIG_PATH = _CORE / "posthog.toml"
ENV_PERSONAL_API_KEY = "POSTHOG_PERSONAL_API_KEY"
_REDACTED = "[REDACTED]"
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_MAX_BYTES = 1_048_576
_LOOPBACK_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "[::1]",
    }
)
_TOML_SECRET_KEYS = frozenset(
    {
        "personal_api_key",
        "api_key",
        "token",
        "secret",
        "password",
        "authorization",
    }
)
_AUTH_ASSIGNMENT = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)\S+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(POSTHOG_PERSONAL_API_KEY|personal_api_key|api_key|token)\s*[:=]\s*\S+"
)
_POSTHOG_KEY = re.compile(r"\bph[xc]_[A-Za-z0-9]+\b")

NEVER_CAPTURE_FIELDS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "authorization",
        "cookie",
        "cookies",
        "payment",
        "card_number",
        "cvv",
        "cvc",
        "secret",
        "client_secret",
        "client_credentials",
        "api_key",
        "apikey",
        "personal_api_key",
    }
)


class QuotaAvailability(str, Enum):
    """Quota/usage availability. Unavailable → UNKNOWN, never pretend zero."""

    UNKNOWN = "UNKNOWN"
    AVAILABLE = "AVAILABLE"
    EXHAUSTED = "EXHAUSTED"


class ProviderResultStatus(str, Enum):
    OK = "ok"
    UNKNOWN = "UNKNOWN"


class PostHogError(RuntimeError):
    """Local/config/provider failure. Message text never includes secrets."""

    def __init__(
        self,
        message: str = "",
        *,
        kind: str | None = None,
        retry_after_seconds: float | None = None,
        secret: str | None = None,
    ) -> None:
        super().__init__(_redact(str(message), secret))
        self.kind = kind
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class PrivacyDefaults:
    mask_sensitive_inputs: bool = True
    session_replay_mask_all_inputs: bool = True
    session_replay_enabled_by_default: bool = False
    prefer_pseudonymous_ids: bool = True
    allow_email_phone_name: bool = False
    never_capture: frozenset[str] = field(
        default_factory=lambda: frozenset(NEVER_CAPTURE_FIELDS)
    )


@dataclass(frozen=True)
class PostHogConfig:
    project_id: str
    host: str
    personal_api_key: str | None = field(default=None, repr=False)
    enabled: bool = False
    runtime_automation_enabled: bool = False
    free_tier_preferred: bool = True
    region: str = ""
    privacy: PrivacyDefaults = field(default_factory=PrivacyDefaults)
    timeout_seconds: float = _DEFAULT_TIMEOUT
    max_response_bytes: int = _DEFAULT_MAX_BYTES

    def __post_init__(self) -> None:
        if self.host:
            object.__setattr__(self, "host", validate_host(self.host))
        if self.runtime_automation_enabled and not self.free_tier_preferred:
            raise ValueError("runtime automation requires free_tier_preferred")

    def __repr__(self) -> str:
        return f"PostHogConfig({self.safe_dict()!r})"

    def __str__(self) -> str:
        return repr(self)

    def safe_dict(self) -> dict[str, Any]:
        """Serialize config with secrets redacted for logs / prompts."""
        return {
            "project_id": self.project_id,
            "host": self.host,
            "region": self.region,
            "enabled": self.enabled,
            "runtime_automation_enabled": self.runtime_automation_enabled,
            "free_tier_preferred": self.free_tier_preferred,
            "personal_api_key": _REDACTED if self.personal_api_key else None,
            "timeout_seconds": self.timeout_seconds,
            "max_response_bytes": self.max_response_bytes,
            "privacy": {
                "mask_sensitive_inputs": self.privacy.mask_sensitive_inputs,
                "session_replay_mask_all_inputs": (
                    self.privacy.session_replay_mask_all_inputs
                ),
                "session_replay_enabled_by_default": (
                    self.privacy.session_replay_enabled_by_default
                ),
                "prefer_pseudonymous_ids": self.privacy.prefer_pseudonymous_ids,
                "allow_email_phone_name": self.privacy.allow_email_phone_name,
                "never_capture": sorted(self.privacy.never_capture),
            },
        }


@dataclass(frozen=True)
class QuotaInfo:
    status: QuotaAvailability
    used: int | None = None
    limit: int | None = None


@dataclass(frozen=True)
class ProviderResult:
    status: ProviderResultStatus
    problems: tuple[dict[str, Any], ...] | None = None
    error_kind: str | None = None
    retry_after_seconds: float | None = None
    rate_limit_remaining: int | None = None


Transport = Callable[[Request], Any]


def validate_host(host: str) -> str:
    """Accept only https base URLs safe for PostHog Cloud endpoints."""
    text = str(host or "").strip()
    if not text:
        raise ValueError("posthog host is required")
    lower = text.casefold()
    if lower.startswith("file:") or lower.startswith("javascript:"):
        raise ValueError("posthog host scheme is not allowed")
    if "://" not in text:
        raise ValueError("posthog host must be an absolute https URL")

    parsed = urlparse(text)
    if parsed.scheme.casefold() != "https":
        raise ValueError("posthog host must use https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("posthog host must not embed credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("posthog host must not include query or fragment")

    hostname = (parsed.hostname or "").casefold()
    if not hostname:
        raise ValueError("posthog host is missing hostname")
    if hostname in _LOOPBACK_HOSTS or hostname.endswith(".localhost"):
        raise ValueError("localhost is not a PostHog Cloud endpoint")

    path = parsed.path or ""
    if path not in ("", "/"):
        raise ValueError("posthog host must be an origin base URL")

    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{hostname}{port}"


def load_posthog_config(
    path: Path | None = None,
    *,
    personal_api_key: str | None = None,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> PostHogConfig:
    """Load safe PostHog defaults; secrets only from env or injection."""
    config_path = path or DEFAULT_CONFIG_PATH
    raw = load_toml(Path(config_path)) if Path(config_path).is_file() else {}
    if overrides:
        raw = {**raw, **dict(overrides)}

    # Toml must never supply secrets — drop any secret-shaped keys.
    for key in list(raw):
        if str(key).casefold() in _TOML_SECRET_KEYS:
            raw.pop(key, None)

    privacy_raw = raw.get("privacy") if isinstance(raw.get("privacy"), dict) else {}
    privacy = PrivacyDefaults(
        mask_sensitive_inputs=_explicit_bool(
            privacy_raw.get("mask_sensitive_inputs"), True
        ),
        session_replay_mask_all_inputs=_explicit_bool(
            privacy_raw.get("session_replay_mask_all_inputs"), True
        ),
        session_replay_enabled_by_default=_explicit_bool(
            privacy_raw.get("session_replay_enabled_by_default"), False
        ),
        prefer_pseudonymous_ids=_explicit_bool(
            privacy_raw.get("prefer_pseudonymous_ids"), True
        ),
        allow_email_phone_name=_explicit_bool(
            privacy_raw.get("allow_email_phone_name"), False
        ),
        never_capture=_never_capture_from(privacy_raw.get("never_capture")),
    )

    host_raw = str(raw.get("host") or "").strip()
    host = validate_host(host_raw) if host_raw else ""

    env = environ if environ is not None else os.environ
    secret = personal_api_key
    if secret is None:
        secret = env.get(ENV_PERSONAL_API_KEY) or None
    if secret is not None:
        secret = str(secret).strip() or None

    return PostHogConfig(
        project_id=str(raw.get("project_id") or "").strip(),
        host=host,
        personal_api_key=secret,
        enabled=_explicit_bool(raw.get("enabled"), False),
        runtime_automation_enabled=_explicit_bool(
            raw.get("runtime_automation_enabled"), False
        ),
        free_tier_preferred=_explicit_bool(raw.get("free_tier_preferred"), True),
        region=str(raw.get("region") or "").strip(),
        privacy=privacy,
        timeout_seconds=_positive_float(raw.get("timeout_seconds"), _DEFAULT_TIMEOUT),
        max_response_bytes=_positive_int(
            raw.get("max_response_bytes"), _DEFAULT_MAX_BYTES
        ),
    )


def config_from_profile(
    profile: Mapping[str, Any],
    *,
    personal_api_key: str | None = None,
    environ: Mapping[str, str] | None = None,
    base: Path | None = None,
) -> PostHogConfig:
    """Merge optional profile [observability] onto core PostHog defaults."""
    base_cfg = load_posthog_config(
        base,
        personal_api_key=personal_api_key,
        environ=environ,
    )
    obs = profile.get("observability")
    if not isinstance(obs, dict):
        return base_cfg
    safe_obs = {
        key: value
        for key, value in obs.items()
        if str(key).casefold() not in _TOML_SECRET_KEYS
    }
    project_id = str(safe_obs.get("id") or base_cfg.project_id).strip()
    host_raw = str(safe_obs.get("host") or base_cfg.host).strip()
    host = validate_host(host_raw) if host_raw else base_cfg.host
    region = str(safe_obs.get("region") or base_cfg.region).strip()
    return replace(
        base_cfg,
        project_id=project_id,
        host=host,
        region=region,
    )


class PostHogClient:
    """Injectable stdlib urllib client with bounded JSON responses."""

    def __init__(
        self,
        config: PostHogConfig,
        *,
        transport: Transport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    def get_quota(self) -> QuotaInfo:
        """Read quota/usage when available; UNKNOWN when not (never zero)."""
        if not self._config.project_id or not self._config.host:
            return QuotaInfo(status=QuotaAvailability.UNKNOWN)
        try:
            payload = self._get_json(f"/api/projects/{self._config.project_id}/")
        except PostHogError:
            return QuotaInfo(status=QuotaAvailability.UNKNOWN)
        except Exception as exc:  # noqa: BLE001 — normalize to UNKNOWN
            _LOG.warning(
                "posthog quota unavailable: %s",
                _redact(str(exc), self._config.personal_api_key),
            )
            return QuotaInfo(status=QuotaAvailability.UNKNOWN)

        if not isinstance(payload, dict):
            return QuotaInfo(status=QuotaAvailability.UNKNOWN)

        used = _optional_int(payload.get("usage") or payload.get("used"))
        limit = _optional_int(payload.get("limit") or payload.get("quota"))
        if used is None and limit is None:
            return QuotaInfo(status=QuotaAvailability.UNKNOWN)
        if limit is not None and used is not None and used >= limit:
            return QuotaInfo(status=QuotaAvailability.EXHAUSTED, used=used, limit=limit)
        return QuotaInfo(status=QuotaAvailability.AVAILABLE, used=used, limit=limit)

    def list_problems(self) -> ProviderResult:
        """Fetch problem signals. Provider failure → UNKNOWN, not []."""
        if not self._config.host or not self._config.project_id:
            return ProviderResult(
                status=ProviderResultStatus.UNKNOWN,
                problems=None,
                error_kind="network",
            )
        try:
            payload = self._get_json(
                f"/api/projects/{self._config.project_id}/error_tracking/issues/"
            )
        except PostHogError as exc:
            return ProviderResult(
                status=ProviderResultStatus.UNKNOWN,
                problems=None,
                error_kind=exc.kind or "network",
                retry_after_seconds=exc.retry_after_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning(
                "posthog list_problems failed: %s",
                _redact(str(exc), self._config.personal_api_key),
            )
            return ProviderResult(
                status=ProviderResultStatus.UNKNOWN,
                problems=None,
                error_kind="network",
            )

        problems = _problems_from_payload(payload)
        if problems is None:
            return ProviderResult(
                status=ProviderResultStatus.UNKNOWN,
                problems=None,
                error_kind="invalid_payload",
            )
        return ProviderResult(
            status=ProviderResultStatus.OK,
            problems=problems,
        )

    def request_json(self, path: str) -> Any:
        """Low-level JSON GET for callers that need explicit errors."""
        return self._get_json(path)

    def _get_json(self, path: str) -> Any:
        url = self._url(path)
        headers = {
            "Accept": "application/json",
            "User-Agent": "nexus-harness-posthog-boundary/1",
        }
        secret = self._config.personal_api_key
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        request = Request(url, headers=headers, method="GET")
        opener = self._transport or _make_default_transport(
            self._config.timeout_seconds
        )
        try:
            response = opener(request)
        except HTTPError as exc:
            raise _from_http_error(exc) from None
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise PostHogError(
                f"network unavailable: {reason}",
                kind="network",
                secret=secret,
            ) from None
        except TimeoutError:
            raise PostHogError(
                "network unavailable: timeout",
                kind="network",
            ) from None
        except OSError as exc:
            raise PostHogError(
                f"network unavailable: {exc}",
                kind="network",
                secret=secret,
            ) from None

        try:
            body = _read_bounded(response, self._config.max_response_bytes)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PostHogError(
                "invalid payload from PostHog",
                kind="invalid_payload",
            ) from exc

    def _url(self, path: str) -> str:
        base = self._config.host.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return base + path


def _make_default_transport(timeout: float) -> Transport:
    def _transport(request: Request):
        return urlopen(request, timeout=timeout)  # noqa: S310

    return _transport


def _read_bounded(response: Any, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(65536, max(1, max_bytes - total + 1)))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PostHogError(
                "response exceeded bounded size",
                kind="invalid_payload",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _from_http_error(exc: HTTPError) -> PostHogError:
    code = int(getattr(exc, "code", 0) or 0)
    retry_after = _parse_retry_after(getattr(exc, "headers", None))
    # Drain/close the error body without logging it.
    try:
        exc.read()
    except Exception:  # noqa: BLE001
        pass
    try:
        exc.close()
    except Exception:  # noqa: BLE001
        pass
    if code in {401, 403}:
        return PostHogError("authentication error", kind="authentication")
    if code == 429:
        return PostHogError(
            "rate limit",
            kind="rate_limit",
            retry_after_seconds=retry_after,
        )
    if 500 <= code <= 599:
        return PostHogError("provider server error", kind="server")
    return PostHogError(f"provider HTTP {code}", kind="network")


def _parse_retry_after(headers: Any) -> float | None:
    if headers is None:
        return None
    try:
        raw = headers.get("Retry-After")
    except Exception:  # noqa: BLE001
        return None
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def _problems_from_payload(payload: Any) -> tuple[dict[str, Any], ...] | None:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("results")
        if items is None:
            items = payload.get("problems")
        if items is None and "id" in payload:
            items = [payload]
    else:
        return None
    if not isinstance(items, list):
        return None
    problems: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            problems.append(dict(item))
        else:
            return None
    return tuple(problems)


def _never_capture_from(raw: Any) -> frozenset[str]:
    if raw is None or not isinstance(raw, list):
        return frozenset(NEVER_CAPTURE_FIELDS)
    items = {str(item).strip().casefold() for item in raw if str(item).strip()}
    return frozenset(items) | frozenset(
        item.casefold() for item in NEVER_CAPTURE_FIELDS
    )


def _explicit_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError("boolean config fields must be explicit booleans")


def _positive_float(value: Any, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("timeout must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout must be a number") from exc
    if number <= 0:
        raise ValueError("timeout must be positive")
    return number


def _positive_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("max_response_bytes must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_response_bytes must be an integer") from exc
    if number <= 0:
        raise ValueError("max_response_bytes must be positive")
    return number


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _redact(text: str, secret: str | None = None) -> str:
    out = str(text or "")
    if secret:
        out = out.replace(secret, _REDACTED)
    out = _AUTH_ASSIGNMENT.sub(r"\1" + _REDACTED, out)
    out = _SECRET_ASSIGNMENT.sub(r"\1=" + _REDACTED, out)
    out = _POSTHOG_KEY.sub(_REDACTED, out)
    return out
