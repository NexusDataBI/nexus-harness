"""Normalize PostHog runtime problems into provider-independent incident candidates."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from nexus_harness.incidents import IncidentCandidate, normalize_posthog_problem

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "posthog-errors.json"


def _load_fixture() -> list[dict]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


class IncidentTests(unittest.TestCase):
    def test_same_error_location_has_stable_fingerprint(self):
        payload = _load_fixture()
        a = normalize_posthog_problem(payload[0])
        b = normalize_posthog_problem(payload[1])
        self.assertEqual(a.fingerprint, b.fingerprint)

    def test_stack_noise_does_not_change_fingerprint(self):
        base = {
            "project": "sdr-platform",
            "environment": "production",
            "error_type": "TypeError",
            "stack_location": "src/leads.ts:fetchLead",
            "route": "/api/leads",
        }
        noisy = {
            **base,
            "stack_location": (
                "src/leads.ts:fetchLead 0x7fff1234abcd "
                "550e8400-e29b-41d4-a716-446655440000"
            ),
        }
        a = normalize_posthog_problem(base)
        b = normalize_posthog_problem(noisy)
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertEqual(a.stack_location, b.stack_location)
        self.assertNotIn("0x", a.stack_location.casefold())
        self.assertNotIn("550e8400", a.stack_location)

    def test_fingerprint_is_deterministic_hex(self):
        payload = _load_fixture()
        a = normalize_posthog_problem(payload[0])
        b = normalize_posthog_problem(payload[0])
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertRegex(a.fingerprint, r"^[0-9a-f]{64}$")

    def test_different_project_environment_or_location_changes_fingerprint(self):
        payload = _load_fixture()
        baseline = normalize_posthog_problem(payload[0])
        other_project = normalize_posthog_problem(payload[2])
        other_env = normalize_posthog_problem(payload[3])
        other_location = normalize_posthog_problem(payload[4])
        other_error = normalize_posthog_problem(payload[5])
        self.assertNotEqual(baseline.fingerprint, other_project.fingerprint)
        self.assertNotEqual(baseline.fingerprint, other_env.fingerprint)
        self.assertNotEqual(baseline.fingerprint, other_location.fingerprint)
        self.assertNotEqual(baseline.fingerprint, other_error.fingerprint)

    def test_volatile_fields_do_not_affect_fingerprint(self):
        payload = _load_fixture()
        a = normalize_posthog_problem(payload[0])
        b = normalize_posthog_problem(payload[1])
        self.assertNotEqual(payload[0]["session_id"], payload[1]["session_id"])
        self.assertNotEqual(payload[0]["request_id"], payload[1]["request_id"])
        self.assertNotEqual(payload[0]["last_seen"], payload[1]["last_seen"])
        self.assertEqual(a.fingerprint, b.fingerprint)

    def test_pii_is_not_hashed_into_fingerprint(self):
        payload = _load_fixture()
        a = normalize_posthog_problem(payload[0])
        b = normalize_posthog_problem(payload[1])
        self.assertNotEqual(payload[0]["user_email"], payload[1]["user_email"])
        self.assertEqual(a.fingerprint, b.fingerprint)
        for value in (
            payload[0]["user_email"],
            payload[0]["user_phone"],
            payload[0]["user_name"],
            payload[1]["user_email"],
            payload[1]["user_phone"],
            payload[1]["user_name"],
        ):
            self.assertNotIn(value.casefold(), a.fingerprint.casefold())

    def test_candidate_is_provider_independent_shape(self):
        payload = _load_fixture()
        candidate = normalize_posthog_problem(payload[0])
        self.assertIsInstance(candidate, IncidentCandidate)
        self.assertEqual(candidate.project, "sdr-platform")
        self.assertEqual(candidate.environment, "production")
        self.assertEqual(candidate.error_type, "TypeError")
        self.assertEqual(
            candidate.stack_location, "src/modules/leads/service.ts:fetchLead"
        )
        self.assertEqual(candidate.route, "/api/leads")
        self.assertEqual(candidate.release, "abc123def")
        self.assertEqual(candidate.occurrences, 4)
        self.assertEqual(candidate.affected_users, 2)
        self.assertEqual(candidate.first_seen, "2026-08-25T10:00:00Z")
        self.assertEqual(candidate.last_seen, "2026-08-25T12:15:00Z")
        self.assertEqual(candidate.provider_problem_id, "err_ph_1001")
        self.assertIn("sess_aaa111", candidate.session_ids)
        self.assertTrue(any("sess_aaa111" in link for link in candidate.session_links))

    def test_root_and_escape_cause_remain_unknown(self):
        payload = _load_fixture()
        candidate = normalize_posthog_problem(payload[0])
        self.assertEqual(candidate.root_cause, "UNKNOWN")
        self.assertEqual(candidate.escape_cause, "UNKNOWN")
        self.assertEqual(candidate.proximate_symptom, "KNOWN")
        self.assertNotRegex(candidate.root_cause, r"(?i)because|caused by|root")
        # Never invent RCA prose
        for attr in ("root_cause", "escape_cause"):
            self.assertEqual(getattr(candidate, attr), "UNKNOWN")

    def test_incomplete_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_posthog_problem({"id": "err-1", "name": "TypeError"})


if __name__ == "__main__":
    unittest.main()
