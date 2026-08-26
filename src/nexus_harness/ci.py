"""Render the self-hosted Nexus Quality Gate GitHub Actions workflow."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_TEMPLATE = _REPO_ROOT / "ci" / "workflow.template.yml"


def render_workflow(template_path: Path | None = None) -> str:
    """Return the Quality Gate workflow YAML as a string.

    Loads ``ci/workflow.template.yml`` by default. Rendering is string/template
    only — no YAML parser in the harness runtime.
    """
    path = template_path if template_path is not None else _DEFAULT_TEMPLATE
    return path.read_text(encoding="utf-8")
