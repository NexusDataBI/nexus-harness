"""Ops cutover/activation docs — repo paths exist; no absolute user homes."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from nexus_harness.adapters import render_all

REPO_ROOT = Path(__file__).resolve().parents[1]
OPS_DOCS = (
    "docs/operations/cutover.md",
    "docs/operations/rollback.md",
    "docs/operations/activation.md",
)
FORBIDDEN_HOME = "/Users/"
REPO_PATH = re.compile(
    r"(?:^|[\s`\"'(=])("
    r"(?:scripts|docs|src|tests|evals|infra|core|skills|profiles|"
    r"adapters|hooks|ci|upstream|dist)/[A-Za-z0-9._/-]+"
    r"|harness\.lock|projects\.toml"
    r")"
)
MODULE_PATH = re.compile(r"python3\s+-m\s+(nexus_harness(?:\.[A-Za-z0-9_]+)+)")
TRAIL = re.compile(r"[.,;:)]+$")
GENERATED_DIST_PREFIXES = (
    "dist/src/nexus_harness",
    "dist/core",
    "dist/hooks",
)


def _ops_text() -> str:
    return "\n".join(
        (REPO_ROOT / relative).read_text(encoding="utf-8") for relative in OPS_DOCS
    )


def _strip(token: str) -> str:
    return TRAIL.sub("", token.strip().strip("`").strip('"').strip("'"))


def _referenced_paths(text: str) -> set[str]:
    found: set[str] = set()
    for match in REPO_PATH.finditer(text):
        found.add(_strip(match.group(1)))
    for match in MODULE_PATH.finditer(text):
        found.add("src/" + match.group(1).replace(".", "/") + ".py")
    return {item for item in found if item and "<" not in item}


def _generated_dist_paths(root: Path) -> set[str]:
    rendered = {f"dist/{item.relative_path}" for item in render_all(root)}
    extra = set(GENERATED_DIST_PREFIXES)
    extra.add("dist/.gitkeep")
    return rendered | extra


def _present(relative: str, generated: set[str]) -> bool:
    path = REPO_ROOT / relative
    if path.exists():
        return True
    if relative in generated:
        return True
    if relative.startswith("dist/"):
        rest = relative.removeprefix("dist/")
        if (REPO_ROOT / "tests" / "golden" / rest).exists():
            return True
        if any(
            relative == prefix or relative.startswith(prefix + "/")
            for prefix in GENERATED_DIST_PREFIXES
        ):
            return True
    return False


class CutoverDocsTests(unittest.TestCase):
    def test_required_ops_docs_exist(self):
        missing = [
            relative for relative in OPS_DOCS if not (REPO_ROOT / relative).is_file()
        ]
        self.assertEqual(missing, [], f"missing ops docs: {missing}")

    def test_ops_docs_do_not_embed_absolute_user_homes(self):
        for relative in OPS_DOCS:
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn(
                FORBIDDEN_HOME,
                text,
                f"{relative} must not contain {FORBIDDEN_HOME!r}",
            )

    def test_referenced_repo_paths_exist(self):
        generated = _generated_dist_paths(REPO_ROOT)
        missing: list[str] = []
        for relative in sorted(_referenced_paths(_ops_text())):
            if not _present(relative, generated):
                missing.append(relative)
        self.assertEqual(missing, [], f"docs reference missing paths: {missing}")

    def test_cutover_documents_backup_order_doctor_and_retention(self):
        cutover = (REPO_ROOT / "docs/operations/cutover.md").read_text(encoding="utf-8")
        rollback = (REPO_ROOT / "docs/operations/rollback.md").read_text(
            encoding="utf-8"
        )
        lowered = (cutover + "\n" + rollback).casefold()
        self.assertIn("scripts/nexus", cutover)
        self.assertIn("doctor", lowered)
        first = cutover.casefold().index("codex first")
        second = cutover.casefold().index("cursor second")
        last = cutover.casefold().index("claude last")
        self.assertLess(first, second)
        self.assertLess(second, last)
        self.assertIn("rollback", lowered)
        self.assertIn("read-only", lowered)
        self.assertIn("NEXUS_BACKUP_ROOT", cutover)

    def test_activation_lists_live_steps_in_order(self):
        text = (REPO_ROOT / "docs/operations/activation.md").read_text(encoding="utf-8")
        lowered = text.casefold()
        markers = (
            "local release",
            "codex",
            "cursor",
            "claude",
            "github",
            "vps",
            "posthog",
            "non-critical",
            "production",
        )
        positions = [lowered.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions), positions)
        self.assertIn("ACTIVATION_REQUIRED", text)
        self.assertIn("NEXUS_GITHUB_PROJECT_ID", text)
        self.assertIn("POSTHOG_PERSONAL_API_KEY", text)
        self.assertIn("<github-project-node-id>", text)
        self.assertIn("<posthog-personal-api-key>", text)


if __name__ == "__main__":
    unittest.main()
