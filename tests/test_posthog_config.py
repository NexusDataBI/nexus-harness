"""PostHog configuration / privacy boundary — network-free unit tests."""

from __future__ import annotations

import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError
from urllib.request import Request

from nexus_harness.posthog import (
    NEVER_CAPTURE_FIELDS,
    PostHogClient,
    PostHogConfig,
    PostHogError,
    ProviderResultStatus,
    QuotaAvailability,
    load_posthog_config,
    validate_host,
)


ROOT = Path(__file__).resolve().parents[1]
CORE_TOML = ROOT / "core" / "observability" / "posthog.toml"
SCHEMA_PATH = ROOT / "core" / "ci" / "profile.schema.json"
SDR_PROFILE = ROOT / "profiles" / "projects" / "sdr-platform.toml"

SECRET = "phx_supersecret_PERSONAL_KEY_do_not_leak"


def _schema_object_ok(instance: dict, schema: dict) -> bool:
    """Minimal additionalProperties / required check (no jsonschema dep)."""
    if schema.get("type") == "object" and isinstance(instance, dict):
        props = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            if any(key not in props for key in instance):
                return False
        for key, sub in props.items():
            if key in instance and sub.get("type") == "object":
                if not _schema_object_ok(instance[key], sub):
                    return False
        for key in schema.get("required") or []:
            if key not in instance:
                return False
        return True
    return True


class PostHogConfigTests(unittest.TestCase):
    def test_personal_api_key_is_never_serialized(self):
        cfg = PostHogConfig(
            project_id="123",
            host="https://us.posthog.com",
            personal_api_key=SECRET,
        )
        values = list(cfg.safe_dict().values())
        flat = json.dumps(cfg.safe_dict())
        self.assertNotIn(SECRET, values)
        self.assertNotIn(SECRET, flat)
        self.assertNotIn(SECRET, str(cfg.safe_dict()))

    def test_personal_api_key_absent_from_logs_and_exceptions(self):
        cfg = PostHogConfig(
            project_id="123",
            host="https://us.posthog.com",
            personal_api_key=SECRET,
        )
        log_buffer = io.StringIO()
        handler = logging.StreamHandler(log_buffer)
        logger = logging.getLogger("nexus_harness.posthog")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            client = PostHogClient(cfg, transport=_failing_transport(SECRET))
            result = client.list_problems()
            self.assertEqual(result.status, ProviderResultStatus.UNKNOWN)
            with self.assertRaises(PostHogError) as raised:
                client.request_json("/api/projects/123/")
            message = str(raised.exception)
        finally:
            logger.removeHandler(handler)

        log_text = log_buffer.getvalue()
        self.assertNotIn(SECRET, log_text)
        self.assertNotIn(SECRET, message)
        self.assertNotIn(SECRET, repr(result))

    def test_secret_only_from_env_or_injected_never_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "posthog.toml"
            path.write_text(
                "enabled = true\n"
                'project_id = "proj-1"\n'
                'host = "https://eu.posthog.com"\n'
                f'personal_api_key = "{SECRET}"\n'
                f'token = "{SECRET}"\n'
                f'api_key = "{SECRET}"\n',
                encoding="utf-8",
            )
            from_toml = load_posthog_config(path, environ={})
            self.assertIsNone(from_toml.personal_api_key)

            from_env = load_posthog_config(
                path,
                environ={"POSTHOG_PERSONAL_API_KEY": SECRET},
            )
            self.assertEqual(from_env.personal_api_key, SECRET)
            self.assertNotIn(SECRET, from_env.safe_dict().values())

            injected = load_posthog_config(
                path,
                personal_api_key=SECRET,
                environ={},
            )
            self.assertEqual(injected.personal_api_key, SECRET)

    def test_enabled_explicit_automation_off_free_tier_preferred(self):
        defaults = load_posthog_config(CORE_TOML, environ={})
        self.assertIs(defaults.enabled, False)
        self.assertIs(defaults.runtime_automation_enabled, False)
        self.assertIs(defaults.free_tier_preferred, True)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "posthog.toml"
            path.write_text(
                'project_id = "x"\nhost = "https://us.posthog.com"\n',
                encoding="utf-8",
            )
            cfg = load_posthog_config(path, environ={})
            self.assertIs(cfg.enabled, False)
            self.assertIs(cfg.runtime_automation_enabled, False)
            self.assertIs(cfg.free_tier_preferred, True)

            path.write_text(
                "enabled = true\n"
                "runtime_automation_enabled = true\n"
                "free_tier_preferred = false\n"
                'project_id = "x"\n'
                'host = "https://us.posthog.com"\n',
                encoding="utf-8",
            )
            explicit = load_posthog_config(path, environ={})
            self.assertIs(explicit.enabled, True)
            self.assertIs(explicit.runtime_automation_enabled, True)
            self.assertIs(explicit.free_tier_preferred, False)

    def test_https_only_host_rejects_unsafe_urls(self):
        validate_host("https://us.posthog.com")
        validate_host("https://eu.posthog.com")
        validate_host("https://us.i.posthog.com")

        rejected = [
            "http://us.posthog.com",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "https://localhost/posthog",
            "https://127.0.0.1/",
            "https://user:pass@us.posthog.com",
            "https://us.posthog.com/../../admin",
            "https://us.posthog.com/path/with/extra",
            "https://us.posthog.com?token=abc",
            "ftp://us.posthog.com",
            "",
            "us.posthog.com",
        ]
        for host in rejected:
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    validate_host(host)

    def test_host_and_region_are_configurable(self):
        us = PostHogConfig(
            project_id="1",
            host="https://us.posthog.com",
            region="us",
        )
        eu = PostHogConfig(
            project_id="1",
            host="https://eu.posthog.com",
            region="eu",
        )
        self.assertEqual(us.host, "https://us.posthog.com")
        self.assertEqual(eu.host, "https://eu.posthog.com")
        self.assertNotEqual(us.host, eu.host)
        source = (ROOT / "src" / "nexus_harness" / "posthog.py").read_text(
            encoding="utf-8"
        )
        # Must not hardcode a single regional hostname as the only option.
        self.assertNotRegex(
            source,
            r'(?m)^\s*DEFAULT_HOST\s*=\s*"https://us\.posthog\.com"\s*$',
        )

    def test_quota_unavailable_is_unknown_not_zero(self):
        cfg = PostHogConfig(
            project_id="123",
            host="https://us.posthog.com",
            personal_api_key=SECRET,
        )
        client = PostHogClient(cfg, transport=_http_error_transport(503, b"down"))
        quota = client.get_quota()
        self.assertEqual(quota.status, QuotaAvailability.UNKNOWN)
        self.assertIsNone(quota.used)
        self.assertIsNone(quota.limit)
        self.assertNotEqual(quota.used, 0)
        self.assertNotEqual(quota.limit, 0)

    def test_injectable_transport_network_free(self):
        cfg = PostHogConfig(
            project_id="123",
            host="https://eu.posthog.com",
            personal_api_key=SECRET,
            enabled=True,
        )
        payload = {"results": [{"id": "err-1"}]}
        body = json.dumps(payload).encode("utf-8")
        transport = MagicMock(return_value=_FakeResponse(body, status=200))
        client = PostHogClient(cfg, transport=transport)
        result = client.list_problems()
        self.assertEqual(result.status, ProviderResultStatus.OK)
        self.assertIsNotNone(result.problems)
        self.assertEqual(len(result.problems), 1)
        transport.assert_called()
        request = transport.call_args.args[0]
        self.assertIsInstance(request, Request)
        self.assertTrue(str(request.full_url).startswith("https://eu.posthog.com"))

    def test_provider_errors_are_unknown_not_empty_incident_list(self):
        cfg = PostHogConfig(
            project_id="123",
            host="https://us.posthog.com",
            personal_api_key=SECRET,
        )
        cases = {
            "authentication": _http_error_transport(401, b"unauthorized"),
            "rate_limit": _http_error_transport(
                429, b"slow down", headers={"Retry-After": "30"}
            ),
            "network": _url_error_transport(),
            "invalid_payload": MagicMock(
                return_value=_FakeResponse(b"not-json{", status=200)
            ),
            "server": _http_error_transport(500, b"boom"),
        }
        for kind, transport in cases.items():
            with self.subTest(kind=kind):
                client = PostHogClient(cfg, transport=transport)
                result = client.list_problems()
                self.assertEqual(result.status, ProviderResultStatus.UNKNOWN)
                self.assertIsNone(result.problems)
                self.assertNotEqual(result.problems, [])
                self.assertEqual(result.error_kind, kind)
                if kind == "rate_limit":
                    self.assertEqual(result.retry_after_seconds, 30.0)

    def test_privacy_defaults_mask_and_never_capture(self):
        cfg = load_posthog_config(CORE_TOML, environ={})
        privacy = cfg.privacy
        self.assertTrue(privacy.mask_sensitive_inputs)
        self.assertTrue(privacy.session_replay_mask_all_inputs)
        self.assertFalse(privacy.session_replay_enabled_by_default)
        self.assertTrue(privacy.prefer_pseudonymous_ids)
        self.assertFalse(privacy.allow_email_phone_name)
        required = {
            "password",
            "token",
            "authorization",
            "cookie",
            "payment",
            "secret",
            "client_secret",
            "api_key",
        }
        capture = {item.casefold() for item in privacy.never_capture}
        for field in required:
            self.assertIn(field, capture)
        for field in NEVER_CAPTURE_FIELDS:
            self.assertIn(field.casefold(), capture)

    def test_core_toml_exists_with_safe_defaults(self):
        self.assertTrue(CORE_TOML.is_file())
        text = CORE_TOML.read_text(encoding="utf-8")
        self.assertNotIn(SECRET, text)
        self.assertNotRegex(text, r"(?i)phx_[A-Za-z0-9]")
        self.assertIn("free_tier_preferred", text)
        self.assertIn("runtime_automation_enabled", text)
        self.assertIn("mask_sensitive_inputs", text)

    def test_ci_profile_schema_optional_observability_without_token(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("observability", schema["properties"])
        self.assertNotIn("observability", schema.get("required", []))
        obs = schema["properties"]["observability"]
        self.assertFalse(obs["additionalProperties"])
        props = obs["properties"]
        self.assertIn("provider", props)
        self.assertIn("id", props)
        self.assertIn("host", props)
        self.assertNotIn("token", props)
        self.assertNotIn("personal_api_key", props)
        self.assertNotIn("api_key", props)
        minimal = {
            "project": {"id": "demo", "repository": "org/demo"},
            "components": {"web": {"paths": ["apps/web/**"]}},
        }
        self.assertTrue(_schema_object_ok(minimal, schema))
        with_obs = {
            **minimal,
            "observability": {
                "provider": "posthog",
                "id": "fixture-project",
                "host": "https://us.posthog.com",
            },
        }
        self.assertTrue(_schema_object_ok(with_obs, schema))
        with_token = {
            **minimal,
            "observability": {
                "provider": "posthog",
                "id": "fixture-project",
                "token": SECRET,
            },
        }
        self.assertFalse(_schema_object_ok(with_token, schema))

    def test_sdr_platform_profile_has_no_real_posthog_ids_or_secrets(self):
        text = SDR_PROFILE.read_text(encoding="utf-8")
        self.assertNotIn("personal_api_key", text)
        self.assertNotIn("phx_", text)
        # Production profile stays unconfigured for PostHog ids.
        self.assertNotRegex(text, r"(?m)^\[observability\]")


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        self._body = body
        self.status = status
        self.headers = headers or {}

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            data, self._body = self._body, b""
            return data
        data, self._body = self._body[:n], self._body[n:]
        return data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error_transport(code: int, body: bytes, headers: dict | None = None):
    def _transport(request: Request):
        raise HTTPError(
            request.full_url,
            code,
            "error",
            headers or {},
            io.BytesIO(body),
        )

    return _transport


def _url_error_transport():
    def _transport(request: Request):
        raise URLError("network down")

    return _transport


def _failing_transport(secret: str):
    def _transport(request: Request):
        raise URLError(f"failed auth {secret}")

    return _transport


if __name__ == "__main__":
    unittest.main()
