"""Release identity / instrumentation contract — network-free unit tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from nexus_harness.observability import release_context
from nexus_harness.posthog import NEVER_CAPTURE_FIELDS


ROOT = Path(__file__).resolve().parents[1]
INSTRUMENTATION = ROOT / "templates" / "posthog" / "INSTRUMENTATION.md"


class ObservabilityTests(unittest.TestCase):
    def test_release_context_contains_commit_and_environment(self):
        data = release_context("abc123", "production", "sdr-platform")
        self.assertEqual(data["release"], "abc123")
        self.assertEqual(data["environment"], "production")
        self.assertEqual(data["project"], "sdr-platform")

    def test_environments_are_distinguishable(self):
        for env in ("production", "staging", "development"):
            data = release_context("sha", env, "demo")
            self.assertEqual(data["environment"], env)
        values = {
            release_context("sha", env, "demo")["environment"]
            for env in ("production", "staging", "development")
        }
        self.assertEqual(values, {"production", "staging", "development"})

    def test_missing_digest_is_explicit_unknown_or_none(self):
        data = release_context("abc123", "staging", "sdr-platform")
        self.assertIn("deployment_digest", data)
        self.assertIn(data["deployment_digest"], (None, "UNKNOWN"))

    def test_invalid_or_mutable_digest_is_rejected(self):
        for digest in ("latest", "main", "sha256:dead", "not-a-digest"):
            with self.assertRaises(ValueError):
                release_context("abc123", "production", "sdr-platform", digest=digest)
        data = release_context("abc123", "staging", "sdr-platform")
        self.assertIn("deployment_digest", data)
        self.assertIn(data["deployment_digest"], (None, "UNKNOWN"))

    def test_digest_route_session_tenant_optional_kwargs(self):
        digest = "sha256:" + ("a" * 64)
        data = release_context(
            "abc123",
            "production",
            "sdr-platform",
            digest=digest,
            route="/api/leads",
            session="sess_pseudo_1",
            tenant="tenant_pseudo_9",
        )
        self.assertEqual(data["deployment_digest"], digest)
        self.assertEqual(data["route"], "/api/leads")
        self.assertEqual(data["session"], "sess_pseudo_1")
        self.assertEqual(data["tenant"], "tenant_pseudo_9")

    def test_release_context_never_includes_secrets(self):
        data = release_context(
            "abc123",
            "production",
            "sdr-platform",
            digest="sha256:" + ("b" * 64),
            route="/checkout",
            session="s1",
            tenant="t1",
        )
        flat = " ".join(str(v).casefold() for v in data.values())
        keys = {str(k).casefold() for k in data}
        for field in NEVER_CAPTURE_FIELDS:
            self.assertNotIn(field, keys)
            self.assertNotIn(field, flat)
        for banned in (
            "password",
            "authorization",
            "cookie",
            "api_key",
            "token",
            "secret",
            "phx_",
            "bearer ",
        ):
            self.assertNotIn(banned, keys)
            self.assertFalse(
                any(banned in str(v).casefold() for v in data.values()),
                f"secret-shaped value leaked for {banned!r}",
            )

    def test_instrumentation_checklist_template_exists(self):
        self.assertTrue(INSTRUMENTATION.is_file(), f"missing {INSTRUMENTATION}")
        text = INSTRUMENTATION.read_text(encoding="utf-8").casefold()
        required = (
            "product event",
            "error tracking",
            "session replay",
            "release",
            "production",
            "staging",
            "development",
            "pseudonymous",
            "password",
            "authorization",
            "cookie",
        )
        for needle in required:
            self.assertIn(needle, text, f"checklist missing {needle!r}")


if __name__ == "__main__":
    unittest.main()
