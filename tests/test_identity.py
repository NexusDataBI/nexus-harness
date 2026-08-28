"""PR / CI change identity. Public seam: resolve_repo_identity + evaluate_completion."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nexus_harness.completion import evaluate_completion
from nexus_harness.identity import IdentityError, resolve_repo_identity

HEAD_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
HEAD_H = "dddddddddddddddddddddddddddddddddddddddd"
HEAD_H1 = "1111111111111111111111111111111111111111"
HEAD_H2 = "2222222222222222222222222222222222222222"
MERGE_M = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
BASE_B = "cccccccccccccccccccccccccccccccccccccccc"
FORGED = "ffffffffffffffffffffffffffffffffffffffff"


def _pr_event(*, head: str, base: str, merge: str | None = None) -> dict:
    payload = {
        "pull_request": {
            "head": {"sha": head, "repo": {"fork": False}},
            "base": {"sha": base},
        }
    }
    if merge is not None:
        payload["pull_request"]["merge_commit_sha"] = merge
    return payload


def _push_event(*, head: str) -> dict:
    return {"after": head, "head_commit": {"id": head}}


def _ready(*, change_head_sha=None, checkout_sha=None, merge_sha=None, **overrides):
    state = {
        "tracking_required": True,
        "issue": 123,
        "acceptance": [{"id": "AC-1", "status": "PASS", "evidence": "ev-1"}],
        "quality_gate": {"gate": "PASS", "diff_hash": "abc", "report": "structured"},
        "security_gate": {"gate": "PASS", "diff_hash": "abc", "report": "structured"},
        "review_gate": "PASS",
        "current_diff_hash": "abc",
        "verified_diff_hash": "abc",
        "reviewed_diff_hash": "abc",
        "evidence": [
            {
                "id": "ev-1",
                "exit_code": 0,
                "diff_hash": "abc",
                "base_commit": "base",
                "command": "vitest",
            }
        ],
        "findings": [],
    }
    if change_head_sha is not None:
        state["change_head_sha"] = change_head_sha
        state["quality_gate"]["change_head_sha"] = change_head_sha
        state["security_gate"]["change_head_sha"] = change_head_sha
        state["evidence"][0]["change_head_sha"] = change_head_sha
    if checkout_sha is not None:
        state["checkout_sha"] = checkout_sha
    if merge_sha is not None:
        state["merge_sha"] = merge_sha
    state.update(overrides)
    return state


class ResolveRepoIdentityTests(unittest.TestCase):
    def test_local_branch_uses_git_head(self):
        identity = resolve_repo_identity(env={}, git_head=HEAD_A)
        self.assertEqual(identity.change_head_sha, HEAD_A)
        self.assertEqual(identity.checkout_sha, HEAD_A)
        self.assertIsNone(identity.merge_sha)

    def test_github_push_binds_change_head_to_pushed_commit(self):
        identity = resolve_repo_identity(
            env={
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "push",
                "GITHUB_SHA": HEAD_A,
            },
            event=_push_event(head=HEAD_A),
            git_head=HEAD_A,
        )
        self.assertEqual(identity.change_head_sha, HEAD_A)
        self.assertEqual(identity.checkout_sha, HEAD_A)

    def test_pull_request_uses_event_head_not_synthetic_merge(self):
        identity = resolve_repo_identity(
            env={
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_SHA": MERGE_M,
                "CHANGE_HEAD_SHA": FORGED,
                "NEXUS_CHANGE_HEAD_SHA": FORGED,
                "INPUT_HEAD_SHA": FORGED,
            },
            event=_pr_event(head=HEAD_H, base=BASE_B, merge=MERGE_M),
            git_head=MERGE_M,
        )
        self.assertEqual(identity.checkout_sha, MERGE_M)
        self.assertEqual(identity.change_head_sha, HEAD_H)
        self.assertEqual(identity.base_sha, BASE_B)
        self.assertEqual(identity.merge_sha, MERGE_M)
        self.assertNotEqual(identity.change_head_sha, MERGE_M)
        self.assertNotEqual(identity.change_head_sha, FORGED)

    def test_pull_request_event_path_is_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "event.json"
            path.write_text(
                json.dumps(_pr_event(head=HEAD_H, base=BASE_B, merge=MERGE_M)),
                encoding="utf-8",
            )
            identity = resolve_repo_identity(
                env={
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_NAME": "pull_request",
                    "GITHUB_SHA": MERGE_M,
                    "GITHUB_EVENT_PATH": str(path),
                    "CHANGE_HEAD_SHA": FORGED,
                },
                git_head=MERGE_M,
            )
        self.assertEqual(identity.change_head_sha, HEAD_H)
        self.assertEqual(identity.checkout_sha, MERGE_M)

    def test_missing_pull_request_head_fails_closed(self):
        with self.assertRaises(IdentityError):
            resolve_repo_identity(
                env={
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_NAME": "pull_request",
                    "GITHUB_SHA": MERGE_M,
                },
                event={"pull_request": {"head": {}, "base": {"sha": BASE_B}}},
                git_head=MERGE_M,
            )

    def test_invalid_pull_request_head_fails_closed(self):
        with self.assertRaises(IdentityError):
            resolve_repo_identity(
                env={
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_NAME": "pull_request",
                    "GITHUB_SHA": MERGE_M,
                },
                event=_pr_event(head="not-a-sha", base=BASE_B),
                git_head=MERGE_M,
            )

    def test_pull_request_without_event_payload_fails_closed(self):
        with self.assertRaises(IdentityError):
            resolve_repo_identity(
                env={
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_NAME": "pull_request",
                    "GITHUB_SHA": MERGE_M,
                },
                git_head=MERGE_M,
            )

    def test_untrusted_env_does_not_override_event_head(self):
        identity = resolve_repo_identity(
            env={
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_SHA": MERGE_M,
                "CHANGE_HEAD_SHA": FORGED,
                "NEXUS_CHANGE_HEAD_SHA": FORGED,
                "PR_HEAD_SHA": FORGED,
            },
            event=_pr_event(head=HEAD_H, base=BASE_B, merge=MERGE_M),
            git_head=MERGE_M,
        )
        self.assertEqual(identity.change_head_sha, HEAD_H)

    def test_pull_request_target_fails_closed(self):
        with self.assertRaises(IdentityError):
            resolve_repo_identity(
                env={
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_NAME": "pull_request_target",
                    "GITHUB_SHA": BASE_B,
                },
                event=_pr_event(head=HEAD_H, base=BASE_B),
                git_head=BASE_B,
            )


class ChangeHeadFreshnessTests(unittest.TestCase):
    def test_evidence_bound_to_pr_head_is_fresh(self):
        result = evaluate_completion(
            _ready(
                change_head_sha=HEAD_H,
                checkout_sha=MERGE_M,
                merge_sha=MERGE_M,
                base_sha=BASE_B,
            )
        )
        self.assertEqual(result.status, "READY_TO_SHIP", msg=result.reasons)

    def test_evidence_bound_only_to_merge_is_not_change_fresh(self):
        result = evaluate_completion(
            _ready(
                change_head_sha=HEAD_H,
                checkout_sha=MERGE_M,
                merge_sha=MERGE_M,
                quality_gate={
                    "gate": "PASS",
                    "diff_hash": "abc",
                    "change_head_sha": MERGE_M,
                    "report": "structured",
                },
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("fresh" in reason for reason in result.reasons),
            msg=result.reasons,
        )

    def test_legacy_diff_hash_matching_merge_is_not_change_fresh(self):
        result = evaluate_completion(
            _ready(
                change_head_sha=HEAD_H,
                checkout_sha=MERGE_M,
                merge_sha=MERGE_M,
                quality_gate={"gate": "PASS", "diff_hash": MERGE_M, "report": "q"},
                security_gate={
                    "gate": "PASS",
                    "diff_hash": "abc",
                    "change_head_sha": HEAD_H,
                    "report": "s",
                },
                evidence=[
                    {
                        "id": "ev-1",
                        "exit_code": 0,
                        "diff_hash": "abc",
                        "base_commit": "base",
                        "change_head_sha": HEAD_H,
                    }
                ],
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any("quality" in reason and "fresh" in reason for reason in result.reasons),
            msg=result.reasons,
        )

    def test_stale_pr_head_evidence_fails(self):
        result = evaluate_completion(
            _ready(
                change_head_sha=HEAD_H2,
                checkout_sha=MERGE_M,
                quality_gate={
                    "gate": "PASS",
                    "diff_hash": "abc",
                    "change_head_sha": HEAD_H1,
                    "report": "structured",
                },
                security_gate={
                    "gate": "PASS",
                    "diff_hash": "abc",
                    "change_head_sha": HEAD_H1,
                    "report": "structured",
                },
                evidence=[
                    {
                        "id": "ev-1",
                        "exit_code": 0,
                        "diff_hash": "abc",
                        "base_commit": "base",
                        "change_head_sha": HEAD_H1,
                    }
                ],
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("fresh" in reason for reason in result.reasons))

    def test_old_evidence_without_change_head_is_not_promoted(self):
        result = evaluate_completion(
            _ready(
                change_head_sha=HEAD_H,
                checkout_sha=MERGE_M,
                evidence=[
                    {
                        "id": "ev-1",
                        "exit_code": 0,
                        "diff_hash": "abc",
                        "base_commit": "base",
                    }
                ],
            )
        )
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(
            any(
                "evidence" in reason and "fresh" in reason for reason in result.reasons
            ),
            msg=result.reasons,
        )

    def test_legacy_state_without_change_head_still_uses_diff_hash(self):
        result = evaluate_completion(_ready())
        self.assertEqual(result.status, "READY_TO_SHIP")
        self.assertEqual(result.reasons, [])


if __name__ == "__main__":
    unittest.main()
