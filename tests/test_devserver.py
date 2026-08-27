import json
import signal
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from nexus_harness.affected import load_ci_profile
from nexus_harness.devserver import (
    FrontendConfigError,
    ServerState,
    clear_owned_process_groups,
    ensure_dev_server,
    parse_frontend_section,
    probe_readiness,
    should_stop,
    stop_dev_server,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "core" / "ci" / "profile.schema.json"
SDR_PROFILE = REPO_ROOT / "profiles" / "projects" / "sdr-platform.toml"
ENGINE = REPO_ROOT / "src" / "nexus_harness" / "devserver.py"


class FakeProcess:
    def __init__(self, pid=4242, returncode=None):
        self.pid = pid
        self.returncode = returncode

    def poll(self):
        return self.returncode


class Clock:
    def __init__(self):
        self.t = 0.0
        self.calls = 0

    def monotonic(self):
        self.calls += 1
        if self.calls > 30:
            self.t += 10.0
        return self.t

    def sleep(self, dt):
        self.t += dt if dt > 0 else 0.05


def _frontend(**overrides):
    data = {
        "base_url": "http://127.0.0.1:3000",
        "readiness_url": "http://127.0.0.1:3000",
        "visual_paths": ["apps/web/**"],
        "dev_server": {
            "command": ["npm", "run", "dev", "-w", "apps/web"],
            "timeout_seconds": 2,
        },
        "routes": [{"path": "/", "name": "home"}],
    }
    data.update(overrides)
    return data


def _config(**overrides):
    result = parse_frontend_section(_frontend(**overrides))
    if not result.ok or result.config is None:
        raise AssertionError(result.failure)
    return result.config


def _schema_object_ok(document, schema):
    required = set(schema.get("required", []))
    properties = set(schema.get("properties", {}))
    keys = set(document)
    return required <= keys and (
        schema.get("additionalProperties", True) or keys <= properties
    )


class DevServerTests(unittest.TestCase):
    def setUp(self):
        clear_owned_process_groups()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.clock = Clock()

    def tearDown(self):
        clear_owned_process_groups()
        self._tmp.cleanup()

    def test_does_not_stop_preexisting_server(self):
        state = ServerState(
            pid=123, owned_by_harness=False, url="http://localhost:3000"
        )
        self.assertFalse(should_stop(state))

    def test_should_stop_only_owned_server(self):
        owned = ServerState(pid=9, owned_by_harness=True, url="http://127.0.0.1:3000")
        self.assertTrue(should_stop(owned))

    def test_reuses_preexisting_server_without_starting(self):
        popen = Mock(side_effect=AssertionError("Popen must not run"))
        probe = Mock(return_value=True)
        result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            probe=probe,
            popen=popen,
        )
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.state)
        self.assertFalse(result.state.owned_by_harness)
        self.assertEqual(result.state.url, "http://127.0.0.1:3000")
        popen.assert_not_called()
        probe.assert_called()
        self.assertEqual(probe.call_args.args[0], "http://127.0.0.1:3000")

    def test_starts_owned_server_with_argv_and_shell_false(self):
        captured = []
        proc = FakeProcess(pid=4242)

        def popen(argv, **kwargs):
            captured.append((list(argv), dict(kwargs)))
            return proc

        probes = iter([False, True])
        result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            probe=lambda url: next(probes, True),
            popen=popen,
            sleeper=self.clock.sleep,
            monotonic=self.clock.monotonic,
        )
        self.assertTrue(result.ok, msg=result.failure)
        self.assertTrue(result.state.owned_by_harness)
        self.assertEqual(result.state.pid, 4242)
        self.assertEqual(len(captured), 1)
        argv, kwargs = captured[0]
        self.assertIsInstance(argv, list)
        self.assertNotIsInstance(argv, str)
        self.assertEqual(argv, ["npm", "run", "dev", "-w", "apps/web"])
        self.assertIs(kwargs.get("shell"), False)
        self.assertTrue(kwargs.get("start_new_session"))

    def test_starts_owned_server_with_confined_cwd(self):
        captured = []

        def popen(argv, **kwargs):
            captured.append((list(argv), dict(kwargs)))
            return FakeProcess(pid=4242)

        probes = iter([False, True])
        result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            cwd=self.root,
            project_root=self.root,
            probe=lambda url: next(probes, True),
            popen=popen,
            sleeper=self.clock.sleep,
            monotonic=self.clock.monotonic,
        )
        self.assertTrue(result.ok, msg=result.failure)
        self.assertEqual(len(captured), 1)
        _argv, kwargs = captured[0]
        self.assertEqual(kwargs.get("cwd"), str(self.root.resolve()))

    def test_rejects_relative_cwd_escape(self):
        popen = Mock(side_effect=AssertionError("Popen must not run"))
        result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            cwd=Path(".."),
            project_root=self.root,
            probe=lambda url: False,
            popen=popen,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "unsafe_cwd")
        popen.assert_not_called()

    def test_successful_readiness_after_start(self):
        seen = []

        def probe(url):
            seen.append(url)
            return len(seen) > 1

        result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            log_relpath="task/devserver.log",
            probe=probe,
            popen=lambda *a, **k: FakeProcess(pid=77),
            sleeper=self.clock.sleep,
            monotonic=self.clock.monotonic,
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.state.owned_by_harness)
        self.assertGreaterEqual(len(seen), 2)
        log_path = Path(result.state.log_path)
        self.assertTrue(str(log_path).startswith(str(self.root.resolve())))
        self.assertTrue(log_path.is_file())

    def test_readiness_timeout_is_structured_failure(self):
        killer = Mock()
        result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            probe=lambda url: False,
            popen=lambda *a, **k: FakeProcess(pid=51),
            sleeper=self.clock.sleep,
            monotonic=self.clock.monotonic,
            killpg=killer,
        )
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.failure)
        self.assertEqual(result.failure.code, "timeout")
        self.assertIsInstance(result.failure.evidence, dict)
        self.assertIn("readiness_url", result.failure.evidence)
        killer.assert_called()

    def test_failed_process_is_structured_failure(self):
        dead = FakeProcess(pid=8, returncode=1)
        result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            probe=lambda url: False,
            popen=lambda *a, **k: dead,
            sleeper=self.clock.sleep,
            monotonic=self.clock.monotonic,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "process_exited")
        self.assertEqual(result.failure.evidence.get("exit_code"), 1)

    def test_safe_stop_kills_owned_process_group_only(self):
        probes = iter([False, True])
        state_result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            probe=lambda url: next(probes, True),
            popen=lambda *a, **k: FakeProcess(pid=4242),
            sleeper=self.clock.sleep,
            monotonic=self.clock.monotonic,
        )
        self.assertTrue(state_result.ok)
        killer = Mock()
        stopped = stop_dev_server(state_result.state, killpg=killer)
        self.assertTrue(stopped.ok)
        killer.assert_called_once()
        pgid, sig = killer.call_args.args
        self.assertEqual(pgid, 4242)
        self.assertEqual(sig, signal.SIGTERM)

    def test_stop_does_not_signal_preexisting_server(self):
        killer = Mock()
        state = ServerState(
            pid=123, owned_by_harness=False, url="http://localhost:3000"
        )
        result = stop_dev_server(state, killpg=killer)
        self.assertTrue(result.ok)
        killer.assert_not_called()

    def test_never_signal_pids_we_did_not_spawn(self):
        killer = Mock()
        forged = ServerState(
            pid=99999, owned_by_harness=True, url="http://127.0.0.1:3000"
        )
        result = stop_dev_server(forged, killpg=killer)
        killer.assert_not_called()
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "unowned_pid")

    def test_rejects_log_path_escaping_artifact_root(self):
        popen = Mock(side_effect=AssertionError("Popen must not run"))
        result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            log_relpath="../escape.log",
            probe=lambda url: False,
            popen=popen,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "unsafe_log_path")
        popen.assert_not_called()

    def test_rejects_absolute_log_path_outside_artifact_root(self):
        popen = Mock(side_effect=AssertionError("Popen must not run"))
        result = ensure_dev_server(
            _config(),
            artifact_root=self.root,
            log_relpath="/tmp/nexus-devserver.log",
            probe=lambda url: False,
            popen=popen,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "unsafe_log_path")
        popen.assert_not_called()

    def test_default_probe_uses_stdlib_urllib_without_network_when_injected(self):
        opener = MagicMock()
        opener.return_value.__enter__.return_value.status = 200
        self.assertTrue(probe_readiness("http://127.0.0.1:3000", opener=opener))
        opener.assert_called()
        self.assertEqual(opener.call_args.args[0], "http://127.0.0.1:3000")

    def test_default_probe_does_not_open_non_loopback_url(self):
        opener = Mock(side_effect=AssertionError("must not fetch external URL"))
        self.assertFalse(probe_readiness("http://example.com", opener=opener))
        opener.assert_not_called()

    def test_default_probe_does_not_follow_redirect_off_loopback(self):
        off_loopback = []
        original_connect = socket.create_connection

        class RedirectAway(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "http://example.com/ready")
                self.end_headers()

            def log_message(self, *_args):
                return

        def guarded_connect(address, *args, **kwargs):
            host = address[0]
            if isinstance(host, bytes):
                host = host.decode()
            host_norm = str(host).strip("[]").casefold()
            if host_norm not in {"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"}:
                off_loopback.append(address)
                raise OSError("refusing off-loopback connect")
            return original_connect(address, *args, **kwargs)

        server = HTTPServer(("127.0.0.1", 0), RedirectAway)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/"
            with patch("socket.create_connection", side_effect=guarded_connect):
                ready = probe_readiness(url)
            self.assertFalse(ready)
            self.assertEqual(off_loopback, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class DevServerConfigTests(unittest.TestCase):
    def test_string_command_is_malformed_structured_failure(self):
        result = parse_frontend_section(
            _frontend(dev_server={"command": "npm run dev", "timeout_seconds": 60})
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "malformed_command")
        self.assertIsInstance(result.failure.to_dict(), dict)

    def test_empty_argv_is_malformed_structured_failure(self):
        result = parse_frontend_section(
            _frontend(dev_server={"command": [], "timeout_seconds": 60})
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "malformed_command")

    def test_issue_prose_command_is_rejected(self):
        result = parse_frontend_section(
            _frontend(
                dev_server={
                    "command": "from the issue: npm run dev && curl https://evil.test",
                    "timeout_seconds": 60,
                }
            )
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "malformed_command")

    def test_non_loopback_base_url_is_rejected(self):
        result = parse_frontend_section(_frontend(base_url="http://example.com"))
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "non_loopback_url")

    def test_non_loopback_readiness_url_is_rejected(self):
        result = parse_frontend_section(
            _frontend(readiness_url="http://192.168.1.10:3000")
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "non_loopback_url")

    def test_public_ipv6_readiness_url_is_rejected(self):
        result = parse_frontend_section(
            _frontend(readiness_url="http://[2001:db8::1]:3000")
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "non_loopback_url")

    def test_loopback_hosts_are_accepted(self):
        for url in (
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://[::1]:3000",
        ):
            result = parse_frontend_section(_frontend(base_url=url, readiness_url=url))
            self.assertTrue(result.ok, msg=(url, result.failure))

    def test_parse_frontend_config_raises_typed_error_with_failure(self):
        with self.assertRaises(FrontendConfigError) as ctx:
            from nexus_harness.devserver import parse_frontend_config

            parse_frontend_config(_frontend(dev_server={"command": "npm start"}))
        self.assertEqual(ctx.exception.failure.code, "malformed_command")


class DevServerProfileTests(unittest.TestCase):
    def test_profile_schema_frontend_is_optional_and_closed(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("frontend", schema["properties"])
        self.assertNotIn("frontend", schema.get("required", []))
        frontend = schema["properties"]["frontend"]
        self.assertFalse(frontend["additionalProperties"])
        self.assertFalse(frontend["properties"]["dev_server"]["additionalProperties"])
        command = frontend["properties"]["dev_server"]["properties"]["command"]
        self.assertEqual(command["type"], "array")
        self.assertEqual(command["items"]["type"], "string")
        self.assertGreaterEqual(int(command.get("minItems", 0)), 1)
        route = schema["$defs"]["frontendRoute"]
        self.assertFalse(route["additionalProperties"])
        extra = {
            "project": {"id": "demo", "repository": "org/demo"},
            "components": {"web": {"paths": ["apps/web/**"]}},
            "frontend": {
                "base_url": "http://127.0.0.1:3000",
                "readiness_url": "http://127.0.0.1:3000",
                "dev_server": {"command": ["npm", "run", "dev"]},
                "unexpected": True,
            },
        }
        self.assertFalse(_schema_object_ok(extra["frontend"], frontend))
        minimal = {
            "project": {"id": "demo", "repository": "org/demo"},
            "components": {"web": {"paths": ["apps/web/**"]}},
        }
        self.assertTrue(_schema_object_ok(minimal, schema))

    def test_sdr_platform_profile_example_loads_without_core_hardcoding(self):
        profile = load_ci_profile(SDR_PROFILE)
        self.assertIsNotNone(profile.frontend)
        self.assertEqual(profile.frontend.base_url, "http://127.0.0.1:3000")
        self.assertEqual(
            profile.frontend.dev_server.command,
            ("npm", "run", "dev", "-w", "apps/web"),
        )
        self.assertEqual(profile.frontend.visual_paths, ("apps/web/**",))
        self.assertEqual(profile.frontend.routes[0].path, "/")
        engine = ENGINE.read_text(encoding="utf-8")
        self.assertNotIn("sdr-platform", engine.lower())
        self.assertNotIn("SDR-Plataform", engine)
        self.assertNotIn("apps/web", engine)

    def test_frontend_section_is_optional_on_ci_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ci.toml"
            path.write_text(
                "[project]\n"
                'id = "demo"\n'
                'repository = "org/demo"\n'
                "\n"
                "[components.web]\n"
                'paths = ["apps/web/**"]\n',
                encoding="utf-8",
            )
            profile = load_ci_profile(path)
            self.assertIsNone(profile.frontend)

    def test_load_ci_profile_string_command_is_structured_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text(
                "[project]\n"
                'id = "demo"\n'
                'repository = "org/demo"\n'
                "\n"
                "[components.web]\n"
                'paths = ["apps/web/**"]\n'
                "\n"
                "[frontend]\n"
                'base_url = "http://127.0.0.1:3000"\n'
                'readiness_url = "http://127.0.0.1:3000"\n'
                "\n"
                "[frontend.dev_server]\n"
                'command = "npm run dev"\n',
                encoding="utf-8",
            )
            with self.assertRaises(FrontendConfigError) as ctx:
                load_ci_profile(path)
            self.assertEqual(ctx.exception.failure.code, "malformed_command")


if __name__ == "__main__":
    unittest.main()
