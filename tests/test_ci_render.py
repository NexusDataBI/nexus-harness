"""Tests for self-hosted Quality Gate workflow rendering."""

from __future__ import annotations

import re
import unittest

from nexus_harness.ci import render_workflow


def _job_body(text: str, job_id: str) -> str:
    """Return YAML body for a top-level job (until next job or EOF)."""
    pattern = rf"(?m)^  {re.escape(job_id)}:\n"
    match = re.search(pattern, text)
    if match is None:
        raise AssertionError(f"job {job_id!r} not found in workflow")
    start = match.end()
    next_job = re.search(r"(?m)^  [A-Za-z0-9_-]+:\n", text[start:])
    end = start + next_job.start() if next_job else len(text)
    return text[start:end]


def _on_block(text: str) -> str:
    match = re.search(r"(?m)^on:\n", text)
    if match is None:
        raise AssertionError("workflow missing top-level on:")
    start = match.end()
    next_top = re.search(r"(?m)^[A-Za-z0-9_-]+:\n", text[start:])
    end = start + next_top.start() if next_top else len(text)
    return text[start:end]


class CiRenderTests(unittest.TestCase):
    def test_workflow_uses_self_hosted_and_cancels_obsolete_prs(self):
        text = render_workflow()
        self.assertIn("self-hosted", text)
        self.assertIn("nexus-ci", text)
        self.assertIn("cancel-in-progress: true", text)
        self.assertNotIn("ubuntu-latest", text)

    def test_triggers_include_pr_lifecycle_and_dispatch(self):
        text = render_workflow()
        on_block = _on_block(text)
        self.assertIn("pull_request:", on_block)
        self.assertIn("workflow_dispatch:", on_block)
        self.assertIn("push:", on_block)

    def test_runs_on_self_hosted_nexus_ci_only(self):
        text = render_workflow()
        self.assertIn("runs-on: [self-hosted, nexus-ci]", text)
        for job_id in ("quality-gate", "build-images"):
            body = _job_body(text, job_id)
            self.assertIn("runs-on: [self-hosted, nexus-ci]", body)

    def test_pr_job_runs_affected_and_batched_quality(self):
        text = render_workflow()
        pr = _job_body(text, "quality-gate")
        self.assertIn("python3 -m nexus_harness ci affected", pr)
        self.assertIn("python3 -m nexus_harness quality run", pr)
        self.assertIn("--base", pr)
        self.assertIn("--head", pr)

    def test_pr_job_does_not_push_images(self):
        text = render_workflow()
        pr = _job_body(text, "quality-gate")
        self.assertNotIn("python3 -m nexus_harness images build", pr)
        self.assertNotIn("nexus images push", pr)
        self.assertNotIn("docker push", pr)
        self.assertNotIn("--push", pr)

    def test_post_merge_build_does_not_rerun_quality_full(self):
        text = render_workflow()
        build = _job_body(text, "build-images")
        self.assertNotIn("nexus quality full", build)
        self.assertNotIn("python3 -m nexus_harness quality run", build)
        self.assertIn("python3 -m nexus_harness images build", build)
        self.assertIn("python3 -m nexus_harness ci affected", build)

    def test_workflow_documents_module_and_wrapper(self):
        text = render_workflow()
        self.assertIn("python3 -m nexus_harness", text)
        self.assertIn("scripts/nexus", text)

    def test_no_workflow_level_paths_filter(self):
        text = render_workflow()
        on_block = _on_block(text)
        self.assertNotIn("paths:", on_block)
        self.assertNotIn("paths-ignore:", on_block)

    def test_required_quality_gate_job_always_exists(self):
        text = render_workflow()
        pr = _job_body(text, "quality-gate")
        # Job must not be skipped when the affected set is empty.
        self.assertNotRegex(pr, r"(?m)^\s+if:\s+.*affected")
        self.assertIn("PASS", pr)
        self.assertIn("FAIL", pr)

    def test_cancel_in_progress_only_for_pr_concurrency(self):
        text = render_workflow()
        pr = _job_body(text, "quality-gate")
        build = _job_body(text, "build-images")
        self.assertIn("cancel-in-progress: true", pr)
        self.assertIn("cancel-in-progress: false", build)

    def test_no_project_secrets_or_client_hosts(self):
        text = render_workflow()
        self.assertNotRegex(text, r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        lowered = text.lower()
        self.assertNotIn("ghcr_token", lowered)
        self.assertNotIn("password:", lowered)


if __name__ == "__main__":
    unittest.main()
