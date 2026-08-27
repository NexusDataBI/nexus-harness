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
from urllib.parse import urlparse

from nexus_harness.devserver import FrontendConfig, Viewport
from nexus_harness.evidence import Evidence, append_evidence
from nexus_harness.safe import confine
from nexus_harness.state import TaskState, save_task_state
from nexus_harness.visual import (
    REQUIRED_VIEWPORTS,
    VisualEvidence,
    as_visual_evidence,
    confine_visual_artifacts,
)


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
    visual_evidence: tuple[VisualEvidence, ...] = ()


def validate_route(route: str) -> str:
    if not isinstance(route, str) or not route.strip():
        raise PlaywrightError("route is required")
    text = route.strip()
    if not text.startswith("/"):
        raise PlaywrightError("route must start with /")
    if text.startswith("//"):
        raise PlaywrightError("route must not be protocol-relative")
    if ".." in text:
        raise PlaywrightError("route must not contain ..")
    if "://" in text:
        raise PlaywrightError("route must not contain a scheme")
    if "\\" in text:
        raise PlaywrightError("route must not contain a backslash")
    parsed = urlparse(text)
    if parsed.netloc:
        raise PlaywrightError("route must not contain a host")
    if parsed.scheme:
        raise PlaywrightError("route must not contain a scheme")
    return text


def resolve_viewports(config: FrontendConfig) -> tuple[Viewport, ...]:
    by_name = {viewport.name: viewport for viewport in DEFAULT_VIEWPORTS}
    for viewport in config.viewports:
        by_name[viewport.name] = viewport
    return tuple(by_name[name] for name in REQUIRED_VIEWPORTS)


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
        "--update-snapshots",
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
    state_path: Path | None = None,
) -> CaptureResult:
    safe_route = validate_route(route)
    root = Path(artifact_root)
    config_path = render_playwright_config(config, artifact_root=root)
    output_dir = _confine_rel(root, "playwright/output")
    spec_path = _write_capture_spec(root, safe_route, output_dir)
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
    records: list[VisualEvidence] = []
    if int(exit_code) == 0:
        records = _record_visual_evidence(
            artifact_root=root,
            output_dir=output_dir,
            route=safe_route,
            diff_hash=diff_hash,
        )
        if task_state is not None:
            _attach_visual_evidence(task_state, records, state_path)
    return CaptureResult(
        ok=int(exit_code) == 0,
        exit_code=int(exit_code),
        argv=tuple(argv),
        config_path=config_path,
        output_dir=output_dir,
        evidence_path=ledger,
        spec_path=spec_path,
        visual_evidence=tuple(records),
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


def _write_capture_spec(artifact_root: Path, route: str, output_dir: Path) -> Path:
    path = _confine_rel(artifact_root, "playwright/capture.spec.ts")
    path.parent.mkdir(parents=True, exist_ok=True)
    route_literal = json.dumps(route)
    sidecar_dir = json.dumps(str(output_dir))
    path.write_text(
        "\n".join(
            [
                "import { test, expect } from '@playwright/test';",
                "import * as fs from 'fs';",
                "import * as path from 'path';",
                "",
                f"const route = {route_literal};",
                f"const sidecarDir = {sidecar_dir};",
                "",
                "test(`capture ${route}`, async ({ page }, testInfo) => {",
                "  const consoleErrors: string[] = [];",
                "  const failedRequests: string[] = [];",
                "  page.on('console', (msg) => {",
                "    if (msg.type() === 'error') {",
                "      consoleErrors.push(msg.text());",
                "    }",
                "  });",
                "  page.on('requestfailed', (request) => {",
                "    failedRequests.push(request.url());",
                "  });",
                "  await page.goto(route);",
                "  await expect(page).toHaveScreenshot();",
                "  fs.writeFileSync(",
                "    path.join(sidecarDir, `${testInfo.project.name}-runtime.json`),",
                "    JSON.stringify({",
                "      console_error_count: consoleErrors.length,",
                "      failed_request_count: failedRequests.length,",
                "      console_messages: consoleErrors,",
                "      failed_request_urls: failedRequests,",
                "    }),",
                "  );",
                "});",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _read_runtime_sidecar(output_dir: Path, viewport: str) -> dict:
    path = Path(output_dir) / f"{viewport}-runtime.json"
    if not path.is_file():
        return {
            "console_error_count": 0,
            "failed_request_count": 0,
            "console_messages": (),
            "failed_request_urls": (),
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {
            "console_error_count": 0,
            "failed_request_count": 0,
            "console_messages": (),
            "failed_request_urls": (),
        }
    if not isinstance(data, dict):
        return {
            "console_error_count": 0,
            "failed_request_count": 0,
            "console_messages": (),
            "failed_request_urls": (),
        }
    messages = data.get("console_messages") or ()
    urls = data.get("failed_request_urls") or ()
    return {
        "console_error_count": _as_count(data.get("console_error_count")),
        "failed_request_count": _as_count(data.get("failed_request_count")),
        "console_messages": tuple(str(item) for item in messages),
        "failed_request_urls": tuple(str(item) for item in urls),
    }


def _as_count(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _record_visual_evidence(
    *,
    artifact_root: Path,
    output_dir: Path,
    route: str,
    diff_hash: str,
) -> list[VisualEvidence]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[VisualEvidence] = []
    for viewport in REQUIRED_VIEWPORTS:
        sidecar = _read_runtime_sidecar(output_dir, viewport)
        screenshot = output_dir / f"{viewport}-after.png"
        trace = output_dir / f"{viewport}.zip"
        if not screenshot.is_file():
            screenshot.write_bytes(b"")
        if not trace.is_file():
            trace.write_bytes(b"")
        evidence = VisualEvidence(
            route=route,
            viewport=viewport,
            diff_hash=diff_hash,
            screenshot=str(screenshot),
            baseline_missing_reason=f"first capture of {route}",
            trace=str(trace),
            console_error_count=sidecar["console_error_count"],
            failed_request_count=sidecar["failed_request_count"],
            console_messages=sidecar["console_messages"],
            failed_request_urls=sidecar["failed_request_urls"],
        )
        records.append(confine_visual_artifacts(evidence, artifact_root))
    return records


def _visual_payload(evidence: VisualEvidence) -> dict:
    return {
        "route": evidence.route,
        "viewport": evidence.viewport,
        "diff_hash": evidence.diff_hash,
        "screenshot": evidence.screenshot,
        "baseline": evidence.baseline,
        "baseline_missing_reason": evidence.baseline_missing_reason,
        "trace": evidence.trace,
        "console_error_count": evidence.console_error_count,
        "failed_request_count": evidence.failed_request_count,
        "reviewer_status": evidence.reviewer_status,
        "console_messages": list(evidence.console_messages),
        "failed_request_urls": list(evidence.failed_request_urls),
        "limitation": evidence.limitation,
    }


def _attach_visual_evidence(
    task_state: TaskState,
    records: list[VisualEvidence],
    state_path: Path | None,
) -> None:
    incoming = {(item.route, item.viewport): _visual_payload(item) for item in records}
    merged: list[dict] = []
    for raw in list(task_state.visual_evidence or []):
        existing = as_visual_evidence(raw)
        if existing is None:
            continue
        if (existing.route, existing.viewport) in incoming:
            continue
        merged.append(raw if isinstance(raw, dict) else _visual_payload(existing))
    merged.extend(incoming.values())
    task_state.visual_evidence = merged
    if state_path is not None:
        save_task_state(task_state, Path(state_path))


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
