"""Localhost frontend server lifecycle: probe, reuse, own, stop.

Commands come only from project-profile argv lists. Process launch is
always ``subprocess.Popen(..., shell=False, start_new_session=True)``.
Readiness and base URLs must be loopback. Logs are confined to a
task-owned artifact root. Only process groups spawned by this module
are signaled.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from nexus_harness.safe import PathSafetyError, confine


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_URL_SCHEMES = frozenset({"http", "https"})
_OWNED_PGIDS: set[int] = set()


@dataclass(frozen=True)
class ServerState:
    pid: int | None
    owned_by_harness: bool
    url: str
    log_path: str | None = None
    pgid: int | None = None


@dataclass(frozen=True)
class FrontendRoute:
    path: str
    name: str = ""


@dataclass(frozen=True)
class Viewport:
    name: str
    width: int
    height: int


@dataclass(frozen=True)
class PlaywrightSpec:
    video: bool = False


@dataclass(frozen=True)
class DevServerSpec:
    command: tuple[str, ...]
    timeout_seconds: int = 60


@dataclass(frozen=True)
class FrontendConfig:
    base_url: str
    readiness_url: str
    dev_server: DevServerSpec
    visual_paths: tuple[str, ...] = ()
    routes: tuple[FrontendRoute, ...] = ()
    viewports: tuple[Viewport, ...] = ()
    playwright: PlaywrightSpec = PlaywrightSpec()


@dataclass(frozen=True)
class DevServerFailure:
    code: str
    message: str
    evidence: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class FrontendParseResult:
    ok: bool
    config: FrontendConfig | None = None
    failure: DevServerFailure | None = None


@dataclass(frozen=True)
class DevServerResult:
    ok: bool
    state: ServerState | None = None
    failure: DevServerFailure | None = None


class FrontendConfigError(ValueError):
    """Malformed frontend profile. Carries a structured failure payload."""

    def __init__(self, failure: DevServerFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


def should_stop(state: ServerState) -> bool:
    return bool(state.owned_by_harness)


def clear_owned_process_groups() -> None:
    _OWNED_PGIDS.clear()


def is_loopback_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    text = url.strip()
    if not text:
        return False
    parsed = urlparse(text)
    if parsed.scheme not in _URL_SCHEMES:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    host = (parsed.hostname or "").casefold()
    return host in _LOOPBACK_HOSTS


def probe_readiness(url: str, *, opener: Callable[..., Any] | None = None) -> bool:
    if not is_loopback_url(url):
        return False
    open_url = opener or _default_open
    try:
        with open_url(url, timeout=1) as response:
            status = getattr(response, "status", None)
            if status is None:
                getcode = getattr(response, "getcode", None)
                status = getcode() if callable(getcode) else 200
            return 200 <= int(status) < 300
    except HTTPError as exc:
        exc.close()
        return False
    except (URLError, TimeoutError, OSError, ValueError, TypeError):
        return False


def parse_frontend_section(raw: object) -> FrontendParseResult:
    if not isinstance(raw, dict):
        return _parse_fail(
            "malformed_command",
            "frontend must be a table",
            {"type": type(raw).__name__},
        )

    base_url = raw.get("base_url")
    readiness_url = raw.get("readiness_url")
    if not isinstance(base_url, str) or not base_url.strip():
        return _parse_fail(
            "non_loopback_url",
            "frontend.base_url must be a loopback URL",
            {"field": "base_url"},
        )
    if not isinstance(readiness_url, str) or not readiness_url.strip():
        return _parse_fail(
            "non_loopback_url",
            "frontend.readiness_url must be a loopback URL",
            {"field": "readiness_url"},
        )
    if not is_loopback_url(base_url):
        return _parse_fail(
            "non_loopback_url",
            "frontend.base_url must be loopback (127.0.0.1, localhost, or ::1)",
            {"field": "base_url", "url": base_url},
        )
    if not is_loopback_url(readiness_url):
        return _parse_fail(
            "non_loopback_url",
            "frontend.readiness_url must be loopback (127.0.0.1, localhost, or ::1)",
            {"field": "readiness_url", "url": readiness_url},
        )

    visual_paths = _string_tuple(raw.get("visual_paths"))
    if visual_paths is None:
        return _parse_fail(
            "malformed_command",
            "frontend.visual_paths must be an array of strings",
            {"field": "visual_paths"},
        )

    routes = _parse_routes(raw.get("routes"))
    if isinstance(routes, DevServerFailure):
        return FrontendParseResult(ok=False, failure=routes)

    spec = _parse_dev_server(raw.get("dev_server"))
    if isinstance(spec, DevServerFailure):
        return FrontendParseResult(ok=False, failure=spec)

    viewports = _parse_viewports(raw.get("viewports"))
    if isinstance(viewports, DevServerFailure):
        return FrontendParseResult(ok=False, failure=viewports)

    playwright = _parse_playwright(raw.get("playwright"))
    if isinstance(playwright, DevServerFailure):
        return FrontendParseResult(ok=False, failure=playwright)

    return FrontendParseResult(
        ok=True,
        config=FrontendConfig(
            base_url=base_url.strip(),
            readiness_url=readiness_url.strip(),
            dev_server=spec,
            visual_paths=visual_paths,
            routes=routes,
            viewports=viewports,
            playwright=playwright,
        ),
    )


def parse_frontend_config(raw: object) -> FrontendConfig:
    result = parse_frontend_section(raw)
    if not result.ok or result.config is None:
        raise FrontendConfigError(
            result.failure
            or DevServerFailure(code="malformed_command", message="invalid frontend")
        )
    return result.config


def load_frontend_config(path: Path | str) -> FrontendConfig:
    from nexus_harness.config import load_toml

    data = load_toml(Path(path))
    raw = data.get("frontend")
    if raw is None:
        raise FrontendConfigError(
            DevServerFailure(
                code="malformed_command",
                message="profile has no [frontend] table",
            )
        )
    return parse_frontend_config(raw)


def ensure_dev_server(
    config: FrontendConfig,
    *,
    artifact_root: Path,
    log_relpath: str = "devserver.log",
    probe: Callable[[str], bool] | None = None,
    popen: Callable[..., Any] | None = None,
    sleeper: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
    killpg: Callable[[int, int], None] | None = None,
    poll_interval: float = 0.1,
) -> DevServerResult:
    if not is_loopback_url(config.base_url) or not is_loopback_url(
        config.readiness_url
    ):
        return _fail(
            "non_loopback_url",
            "readiness and base URLs must be loopback",
            {
                "base_url": config.base_url,
                "readiness_url": config.readiness_url,
            },
        )
    if not _valid_argv(config.dev_server.command):
        return _fail(
            "malformed_command",
            "dev_server.command must be a non-empty argv list",
            {"command_type": type(config.dev_server.command).__name__},
        )

    try:
        log_path = _confine_log(artifact_root, log_relpath)
    except PathSafetyError as exc:
        return _fail(
            "unsafe_log_path",
            "log path escapes the task-owned artifact root",
            {"path": log_relpath, "reason": str(exc)},
        )

    probe_fn = probe or probe_readiness
    if probe_fn(config.readiness_url):
        return DevServerResult(
            ok=True,
            state=ServerState(
                pid=None,
                owned_by_harness=False,
                url=config.base_url,
                log_path=str(log_path),
            ),
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    spawn = popen or subprocess.Popen
    argv = [str(part) for part in config.dev_server.command]
    try:
        with log_path.open("ab") as handle:
            proc = spawn(
                argv,
                shell=False,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
    except OSError as exc:
        return _fail(
            "process_exited",
            "failed to start the profile-defined server command",
            {"error": str(exc)},
        )

    pid = int(getattr(proc, "pid", 0) or 0)
    if pid:
        _OWNED_PGIDS.add(pid)

    sleep_fn = sleeper or time.sleep
    time_fn = monotonic or time.monotonic
    deadline = time_fn() + int(config.dev_server.timeout_seconds)
    while time_fn() < deadline:
        exit_code = _poll(proc)
        if exit_code is not None:
            _OWNED_PGIDS.discard(pid)
            return _fail(
                "process_exited",
                "dev server process exited before readiness",
                {"exit_code": exit_code, "pid": pid, "log_path": str(log_path)},
            )
        if probe_fn(config.readiness_url):
            return DevServerResult(
                ok=True,
                state=ServerState(
                    pid=pid,
                    owned_by_harness=True,
                    url=config.base_url,
                    log_path=str(log_path),
                    pgid=pid,
                ),
            )
        sleep_fn(poll_interval)

    _signal_owned(pid, killpg)
    return _fail(
        "timeout",
        "dev server did not become ready before timeout",
        {
            "readiness_url": config.readiness_url,
            "timeout_seconds": config.dev_server.timeout_seconds,
            "pid": pid,
            "log_path": str(log_path),
        },
    )


def stop_dev_server(
    state: ServerState,
    *,
    killpg: Callable[[int, int], None] | None = None,
) -> DevServerResult:
    if not should_stop(state):
        return DevServerResult(ok=True, state=state)
    pgid = state.pgid if state.pgid is not None else state.pid
    if pgid is None or pgid not in _OWNED_PGIDS:
        return DevServerResult(
            ok=False,
            state=state,
            failure=DevServerFailure(
                code="unowned_pid",
                message="refusing to signal a process the harness did not spawn",
                evidence={"pid": pgid},
            ),
        )
    _signal_owned(pgid, killpg)
    return DevServerResult(
        ok=True,
        state=ServerState(
            pid=state.pid,
            owned_by_harness=False,
            url=state.url,
            log_path=state.log_path,
            pgid=state.pgid,
        ),
    )


def _parse_dev_server(raw: object) -> DevServerSpec | DevServerFailure:
    if not isinstance(raw, dict):
        return DevServerFailure(
            code="malformed_command",
            message="frontend.dev_server must be a table",
            evidence={"type": type(raw).__name__},
        )
    argv = _as_argv(raw.get("command"))
    if argv is None:
        return DevServerFailure(
            code="malformed_command",
            message="frontend.dev_server.command must be a non-empty argv array",
            evidence={"command_type": type(raw.get("command")).__name__},
        )
    timeout = raw.get("timeout_seconds", 60)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        return DevServerFailure(
            code="malformed_command",
            message="frontend.dev_server.timeout_seconds must be a positive integer",
            evidence={"timeout_seconds": timeout},
        )
    return DevServerSpec(command=argv, timeout_seconds=timeout)


def _parse_playwright(raw: object) -> PlaywrightSpec | DevServerFailure:
    if raw is None:
        return PlaywrightSpec()
    if not isinstance(raw, dict):
        return DevServerFailure(
            code="malformed_command",
            message="frontend.playwright must be a table",
            evidence={"type": type(raw).__name__},
        )
    video = raw.get("video", False)
    if not isinstance(video, bool):
        return DevServerFailure(
            code="malformed_command",
            message="frontend.playwright.video must be a boolean",
            evidence={"video": video},
        )
    return PlaywrightSpec(video=video)


def _parse_viewports(raw: object) -> tuple[Viewport, ...] | DevServerFailure:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return DevServerFailure(
            code="malformed_command",
            message="frontend.viewports must be an array of tables",
            evidence={"type": type(raw).__name__},
        )
    viewports: list[Viewport] = []
    for item in raw:
        if not isinstance(item, dict):
            return DevServerFailure(
                code="malformed_command",
                message="frontend.viewports entries must be tables",
            )
        name = item.get("name")
        width = item.get("width")
        height = item.get("height")
        if not isinstance(name, str) or not name.strip():
            return DevServerFailure(
                code="malformed_command",
                message="frontend.viewports[].name is required",
            )
        if isinstance(width, bool) or not isinstance(width, int) or width < 1:
            return DevServerFailure(
                code="malformed_command",
                message="frontend.viewports[].width must be a positive integer",
                evidence={"width": width},
            )
        if isinstance(height, bool) or not isinstance(height, int) or height < 1:
            return DevServerFailure(
                code="malformed_command",
                message="frontend.viewports[].height must be a positive integer",
                evidence={"height": height},
            )
        viewports.append(Viewport(name=name.strip(), width=width, height=height))
    return tuple(viewports)


def _parse_routes(raw: object) -> tuple[FrontendRoute, ...] | DevServerFailure:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return DevServerFailure(
            code="malformed_command",
            message="frontend.routes must be an array of tables",
            evidence={"type": type(raw).__name__},
        )
    routes: list[FrontendRoute] = []
    for item in raw:
        if not isinstance(item, dict):
            return DevServerFailure(
                code="malformed_command",
                message="frontend.routes entries must be tables",
            )
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            return DevServerFailure(
                code="malformed_command",
                message="frontend.routes[].path is required",
            )
        name = item.get("name") or ""
        if not isinstance(name, str):
            return DevServerFailure(
                code="malformed_command",
                message="frontend.routes[].name must be a string",
            )
        routes.append(FrontendRoute(path=path, name=name))
    return tuple(routes)


def _as_argv(value: object) -> tuple[str, ...] | None:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        return None
    if not value:
        return None
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        items.append(item)
    return tuple(items)


def _valid_argv(value: object) -> bool:
    return _as_argv(value) is not None


def _string_tuple(value: object) -> tuple[str, ...] | None:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, list):
        return None
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        items.append(item)
    return tuple(items)


def _confine_log(artifact_root: Path, log_relpath: str) -> Path:
    root = Path(artifact_root)
    raw = Path(log_relpath)
    candidate = raw if raw.is_absolute() else root / raw
    return confine(candidate, root)


def _poll(proc: Any) -> int | None:
    poll = getattr(proc, "poll", None)
    if callable(poll):
        code = poll()
        return int(code) if code is not None else None
    code = getattr(proc, "returncode", None)
    return int(code) if code is not None else None


def _signal_owned(pgid: int, killpg: Callable[[int, int], None] | None) -> None:
    if not pgid or pgid not in _OWNED_PGIDS:
        return
    send = killpg or os.killpg
    try:
        send(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    _OWNED_PGIDS.discard(pgid)


class _NoRedirectHandler(HTTPRedirectHandler):
    """Refuse every 3xx hop so a loopback probe cannot leave loopback."""

    def http_error_302(self, req, fp, code, msg, headers):
        raise HTTPError(req.full_url, code, msg, headers, fp)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _default_open(url: str, timeout: float = 1) -> Any:
    # Empty ProxyHandler ignores HTTP(S)_PROXY / system proxy for this probe.
    opener = build_opener(ProxyHandler({}), _NoRedirectHandler)
    return opener.open(url, timeout=timeout)


def _parse_fail(
    code: str, message: str, evidence: dict[str, object] | None = None
) -> FrontendParseResult:
    return FrontendParseResult(
        ok=False,
        failure=DevServerFailure(code=code, message=message, evidence=evidence or {}),
    )


def _fail(
    code: str, message: str, evidence: dict[str, object] | None = None
) -> DevServerResult:
    return DevServerResult(
        ok=False,
        failure=DevServerFailure(code=code, message=message, evidence=evidence or {}),
    )
