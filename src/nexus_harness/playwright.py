"""Playwright visual-evidence harness: render config, capture routes, ledger.

Playwright is the only baseline E2E tool. The runner is injectable. Unit
tests never download browsers or touch the network. Process launch is
always an argv list with ``shell=False``.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from nexus_harness.devserver import FrontendConfig, Viewport
from nexus_harness.evidence import Evidence, append_evidence
from nexus_harness.safe import confine
from nexus_harness.state import TaskState


DEFAULT_VIEWPORTS = (
    Viewport(name="desktop", width=1280, height=800),
    Viewport(name="mobile", width=390, height=844),
)

Runner = Callable[..., tuple[int, str, str]]


class PlaywrightError(ValueError):
    """Unsafe capture route or missing config template."""


@dataclass(frozen=True)
class CaptureResult:
    ok: bool
    exit_code: int
    argv: tuple[str, ...] = ()
    config_path: Path | None = None
    output_dir: Path | None = None
    evidence_path: Path | None = None
    spec_path: Path | None = None
    failure: str | None = None


def validate_route(route: str) -> str:
    if not isinstance(route, str) or not route.strip():
        raise PlaywrightError("route is required")
    text = route.strip()
    if not text.startswith("/"):
        raise PlaywrightError("route must start with /")
    if ".." in text:
        raise PlaywrightError("route must not contain ..")
    if "://" in text:
        raise PlaywrightError("route must not contain a scheme")
    if "\\" in text:
        raise PlaywrightError("route must not contain a backslash")
    return text


def resolve_viewports(config: FrontendConfig) -> tuple[Viewport, ...]:
    return config.viewports or DEFAULT_VIEWPORTS


def render_playwright_config(
    config: FrontendConfig,
    *,
    artifact_root: Path,
    output_relpath: str = "playwright/nexus.config.ts",
    output_dir_relpath: str = "playwright/output",
    template_path: Path | None = None,
) -> Path:
    root = Path(artifact_root)
    config_path = _confine_rel(root, output_relpath)
    output_dir = _confine_rel(root, output_dir_relpath)
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _render_config_text(
            config,
            config_path=config_path,
            output_dir=output_dir,
            template_path=template_path,
        ),
        encoding="utf-8",
    )
    return config_path


def build_capture_argv(
    *,
    config_path: Path,
    spec_path: Path,
    output_dir: Path,
    route: str,
) -> list[str]:
    return [
        "npx",
        "--no-install",
        "playwright",
        "test",
        "--config",
        str(config_path),
        "--output",
        str(output_dir),
        str(spec_path),
        "--grep",
        re.escape(route),
    ]


def capture_route(
    route: str,
    *,
    config: FrontendConfig,
    artifact_root: Path,
    runner: Runner | None = None,
    task_id: str | None = None,
    task_state: TaskState | None = None,
    evidence_path: Path | None = None,
    project_root: Path | None = None,
) -> CaptureResult:
    safe_route = validate_route(route)
    root = Path(artifact_root)
    config_path = render_playwright_config(config, artifact_root=root)
    output_dir = _confine_rel(root, "playwright/output")
    spec_path = _write_capture_spec(root, safe_route)
    argv = build_capture_argv(
        config_path=config_path,
        spec_path=spec_path,
        output_dir=output_dir,
        route=safe_route,
    )
    run = runner or _default_runner
    cwd = Path(project_root) if project_root is not None else root
    exit_code, _stdout, _stderr = run(list(argv), cwd=cwd)
    ledger = (
        confine(Path(evidence_path), root)
        if evidence_path is not None
        else _confine_rel(root, "evidence.jsonl")
    )
    diff_hash = ""
    if task_state is not None and task_state.current_diff_hash:
        diff_hash = task_state.current_diff_hash
    append_evidence(
        ledger,
        Evidence(
            id=_evidence_id(task_id, safe_route),
            command="playwright",
            exit_code=int(exit_code),
            diff_hash=diff_hash,
            base_commit="",
            summary=json.dumps({"argv": list(argv), "route": safe_route}),
            artifact=str(output_dir),
        ),
    )
    return CaptureResult(
        ok=int(exit_code) == 0,
        exit_code=int(exit_code),
        argv=tuple(argv),
        config_path=config_path,
        output_dir=output_dir,
        evidence_path=ledger,
        spec_path=spec_path,
    )


def _confine_rel(root: Path, relpath: str) -> Path:
    raw = Path(relpath)
    candidate = raw if raw.is_absolute() else Path(root) / raw
    return confine(candidate, root)


def _default_template_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents[2:4]:
        candidate = parent / "templates" / "playwright" / "nexus.config.ts"
        if candidate.is_file():
            return candidate
    raise PlaywrightError("playwright template missing")


def _render_config_text(
    config: FrontendConfig,
    *,
    config_path: Path,
    output_dir: Path,
    template_path: Path | None,
) -> str:
    source = (
        Path(template_path) if template_path is not None else _default_template_path()
    )
    text = source.read_text(encoding="utf-8")
    video = "retain-on-failure" if config.playwright.video else "off"
    replacements = {
        "__NEXUS_BASE_URL__": json.dumps(config.base_url),
        "__NEXUS_OUTPUT_DIR__": json.dumps(str(output_dir)),
        "__NEXUS_TEST_DIR__": json.dumps(str(config_path.parent)),
        "__NEXUS_VIDEO__": json.dumps(video),
        "__NEXUS_PROJECTS__": json.dumps(
            [
                {
                    "name": viewport.name,
                    "use": {
                        "browserName": "chromium",
                        "viewport": {
                            "width": viewport.width,
                            "height": viewport.height,
                        },
                    },
                }
                for viewport in resolve_viewports(config)
            ],
            indent=2,
        ),
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def _write_capture_spec(artifact_root: Path, route: str) -> Path:
    path = _confine_rel(artifact_root, "playwright/capture.spec.ts")
    path.parent.mkdir(parents=True, exist_ok=True)
    route_literal = json.dumps(route)
    path.write_text(
        "\n".join(
            [
                "import { test, expect } from '@playwright/test';",
                "",
                f"const route = {route_literal};",
                "",
                "test(`capture ${route}`, async ({ page }) => {",
                "  await page.goto(route);",
                "  await expect(page).toHaveScreenshot();",
                "});",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _evidence_id(task_id: str | None, route: str) -> str:
    slug = route.strip("/").replace("/", "-") or "root"
    prefix = (task_id or "adhoc").strip() or "adhoc"
    return f"frontend-capture-{prefix}-{slug}"


def _default_runner(
    argv: Sequence[str], *, cwd: Path | None = None
) -> tuple[int, str, str]:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""
