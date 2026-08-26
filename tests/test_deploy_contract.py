"""Restricted client-VM deploy contract — argv allowlist, health gate, rollback."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from nexus_harness.deploy_contract import (
    DeployError,
    DeployRequest,
    parse_deploy_argv,
    resolve_argv,
    run_deploy,
)

ROOT = Path(__file__).resolve().parents[1]
CLIENT_VM = ROOT / "infra" / "client-vm"
NEXUS_DEPLOY = CLIENT_VM / "nexus-deploy"
INSTALL_SH = CLIENT_VM / "install-deploy-user.sh"
README = CLIENT_VM / "README.md"

VALID_DIGEST = "sha256:" + ("a" * 64)
PREV_DIGEST = "sha256:" + ("b" * 64)
BAD_HEALTH_DIGEST = "sha256:" + ("c" * 64)

SERVICE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _services_payload() -> dict:
    return {
        "services": {
            "web": {
                "compose_file": "/opt/app/docker-compose.yml",
                "project_dir": "/opt/app",
                "digest_var": "WEB_IMAGE_DIGEST",
                "image": "ghcr.io/example/app-web",
                "health_url": "http://127.0.0.1:8080/health",
            }
        }
    }


def _write_bound_compose(path: Path, *, digest_var: str = "WEB_IMAGE_DIGEST") -> None:
    """Compose that binds image to digest env (no :latest)."""
    path.write_text(
        f"services:\n  web:\n    image: ghcr.io/example/app-web@${{{digest_var}}}\n",
        encoding="utf-8",
    )


def _prepare_deploy_tmp(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    services_path = tmp_path / "services.json"
    env_path = tmp_path / ".env"
    compose_path = tmp_path / "compose.yml"
    services = _services_payload()
    services["services"]["web"]["env_file"] = str(env_path)
    services["services"]["web"]["compose_file"] = str(compose_path)
    services["services"]["web"]["project_dir"] = str(tmp_path)
    services_path.write_text(json.dumps(services), encoding="utf-8")
    _write_bound_compose(compose_path)
    return services_path, env_path, compose_path, services


class DeployParserTests(unittest.TestCase):
    def test_valid_service_and_digest_accepted(self):
        req = parse_deploy_argv(
            ["deploy", "web", VALID_DIGEST],
            services=_services_payload(),
        )
        self.assertIsInstance(req, DeployRequest)
        self.assertEqual(req.action, "deploy")
        self.assertEqual(req.service, "web")
        self.assertEqual(req.digest, VALID_DIGEST)
        self.assertRegex(req.service, SERVICE_NAME_RE)
        self.assertRegex(req.digest, DIGEST_RE)

    def test_latest_rejected(self):
        with self.assertRaises(DeployError) as ctx:
            parse_deploy_argv(
                ["deploy", "web", "latest"],
                services=_services_payload(),
            )
        self.assertIn("latest", str(ctx.exception).lower())

    def test_unknown_service_rejected(self):
        with self.assertRaises(DeployError) as ctx:
            parse_deploy_argv(
                ["deploy", "api", VALID_DIGEST],
                services=_services_payload(),
            )
        msg = str(ctx.exception).lower()
        self.assertTrue("unknown" in msg or "allowlist" in msg or "service" in msg)

    def test_shell_metacharacters_rejected(self):
        payloads = [
            ["deploy", "web;rm", VALID_DIGEST],
            ["deploy", "web", VALID_DIGEST + ";id"],
            ["deploy", "web$(id)", VALID_DIGEST],
            ["deploy", "web", "sha256:" + ("a" * 63) + "`"],
            ["deploy", "web|evil", VALID_DIGEST],
            ["deploy;reboot", "web", VALID_DIGEST],
        ]
        for argv in payloads:
            with self.subTest(argv=argv):
                with self.assertRaises(DeployError):
                    parse_deploy_argv(argv, services=_services_payload())

    def test_ssh_original_command_accepted(self):
        argv = resolve_argv(
            [],
            ssh_original_command=f"deploy web {VALID_DIGEST}",
        )
        req = parse_deploy_argv(argv, services=_services_payload())
        self.assertEqual(req.service, "web")
        self.assertEqual(req.digest, VALID_DIGEST)

    def test_ssh_original_command_metacharacters_rejected(self):
        with self.assertRaises(DeployError):
            resolve_argv([], ssh_original_command="deploy web;reboot sha256:abc")
        with self.assertRaises(DeployError):
            resolve_argv([], ssh_original_command='deploy web "sha256:abc"')
        # Even if split somehow, digest must still fail parse.
        with self.assertRaises(DeployError):
            parse_deploy_argv(
                resolve_argv([], ssh_original_command="deploy web latest"),
                services=_services_payload(),
            )

    def test_image_without_tag_required(self):
        for bad_image in (
            "ghcr.io/example/app-web:latest",
            "ghcr.io/example/app-web:1.2.3",
            "ghcr.io/example/app-web@" + VALID_DIGEST,
            "latest",
            "",
        ):
            with self.subTest(image=bad_image):
                services = _services_payload()
                services["services"]["web"]["image"] = bad_image
                with self.assertRaises(DeployError) as ctx:
                    parse_deploy_argv(
                        ["deploy", "web", VALID_DIGEST],
                        services=services,
                    )
                msg = str(ctx.exception).lower()
                self.assertTrue(
                    "image" in msg or "tag" in msg or "latest" in msg,
                    msg,
                )


class DeployRollbackTests(unittest.TestCase):
    def test_rollback_when_health_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path, env_path, _, _ = _prepare_deploy_tmp(tmp_path)
            evidence_path = tmp_path / "rollback.json"
            env_path.write_text(f"WEB_IMAGE_DIGEST={PREV_DIGEST}\n", encoding="utf-8")

            compose_calls: list[list[str]] = []

            def fake_compose(argv: list[str]) -> int:
                compose_calls.append(list(argv))
                return 0

            health_results = iter(
                [False, True]
            )  # fail after deploy, pass after rollback

            def fake_health(url: str) -> bool:
                self.assertEqual(url, "http://127.0.0.1:8080/health")
                return next(health_results)

            result = run_deploy(
                ["deploy", "web", BAD_HEALTH_DIGEST],
                services_path=services_path,
                compose_runner=fake_compose,
                health_checker=fake_health,
                evidence_path=evidence_path,
            )

            self.assertEqual(result.status, "ROLLBACK")
            self.assertFalse(result.ok)
            env_text = env_path.read_text(encoding="utf-8")
            self.assertIn(PREV_DIGEST, env_text)
            self.assertNotIn(BAD_HEALTH_DIGEST, env_text)
            self.assertTrue(evidence_path.is_file())
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "ROLLBACK")
            self.assertEqual(evidence["service"], "web")
            self.assertEqual(evidence["attempted_digest"], BAD_HEALTH_DIGEST)
            self.assertEqual(evidence["restored_digest"], PREV_DIGEST)
            # Must recreate the allowlisted service (not arbitrary compose targets).
            self.assertTrue(
                any("web" in c for c in compose_calls),
                f"expected web recreate in {compose_calls}",
            )
            self.assertTrue(
                all(
                    "api" not in tok and ";" not in tok
                    for c in compose_calls
                    for tok in c
                )
            )
            # Health gate — compose success alone is not PASS.
            self.assertNotEqual(result.status, "PASS")
            # Every compose invocation must bind the digest env file.
            for call in compose_calls:
                self.assertIn("--env-file", call, f"missing --env-file in {call}")
                idx = call.index("--env-file")
                self.assertEqual(call[idx + 1], str(env_path))

    def test_rollback_when_pull_fails_after_env_write(self):
        """Forward pull fail → rollback; rollback pull may fail but up must run."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path, env_path, _, _ = _prepare_deploy_tmp(tmp_path)
            evidence_path = tmp_path / "rollback.json"
            env_path.write_text(f"WEB_IMAGE_DIGEST={PREV_DIGEST}\n", encoding="utf-8")

            compose_calls: list[list[str]] = []

            def fake_compose(argv: list[str]) -> int:
                compose_calls.append(list(argv))
                if "pull" in argv:
                    return 1  # ALL pulls fail (forward + rollback)
                return 0  # ups succeed

            result = run_deploy(
                ["deploy", "web", VALID_DIGEST],
                services_path=services_path,
                compose_runner=fake_compose,
                health_checker=lambda url: True,
                evidence_path=evidence_path,
            )

            self.assertEqual(result.status, "ROLLBACK")
            self.assertFalse(result.ok)
            env_text = env_path.read_text(encoding="utf-8")
            self.assertIn(PREV_DIGEST, env_text)
            self.assertNotIn(VALID_DIGEST, env_text)
            self.assertTrue(evidence_path.is_file())
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "ROLLBACK")
            self.assertEqual(evidence["attempted_digest"], VALID_DIGEST)
            self.assertEqual(evidence["restored_digest"], PREV_DIGEST)
            self.assertIn("health_restored", evidence)
            # Rollback must still force-recreate even when pull of previous fails.
            up_calls = [
                c
                for c in compose_calls
                if "up" in c and "--force-recreate" in c and "web" in c
            ]
            self.assertTrue(
                up_calls,
                f"expected up --force-recreate for web after pull miss; got {compose_calls}",
            )
            for call in compose_calls:
                self.assertIn("--env-file", call, f"missing --env-file in {call}")

    def test_successful_deploy_requires_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path, env_path, _, _ = _prepare_deploy_tmp(tmp_path)
            env_path.write_text(f"WEB_IMAGE_DIGEST={PREV_DIGEST}\n", encoding="utf-8")

            compose_calls: list[list[str]] = []

            def fake_compose(argv: list[str]) -> int:
                compose_calls.append(list(argv))
                return 0

            result = run_deploy(
                ["deploy", "web", VALID_DIGEST],
                services_path=services_path,
                compose_runner=fake_compose,
                health_checker=lambda url: True,
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.status, "PASS")
            self.assertIn(VALID_DIGEST, env_path.read_text(encoding="utf-8"))
            self.assertTrue(compose_calls)
            for call in compose_calls:
                self.assertIn("--env-file", call, f"missing --env-file in {call}")
                idx = call.index("--env-file")
                self.assertEqual(call[idx + 1], str(env_path))

    def test_compose_latest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path, env_path, compose_path, _ = _prepare_deploy_tmp(tmp_path)
            env_path.write_text(f"WEB_IMAGE_DIGEST={PREV_DIGEST}\n", encoding="utf-8")
            compose_path.write_text(
                "services:\n  web:\n    image: ghcr.io/example/app-web:latest\n",
                encoding="utf-8",
            )
            result = run_deploy(
                ["deploy", "web", VALID_DIGEST],
                services_path=services_path,
                compose_runner=lambda argv: 0,
                health_checker=lambda url: True,
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.status, "ERROR")
            self.assertIn("latest", result.message.lower())

    def test_compose_missing_digest_var_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path, env_path, compose_path, _ = _prepare_deploy_tmp(tmp_path)
            env_path.write_text(f"WEB_IMAGE_DIGEST={PREV_DIGEST}\n", encoding="utf-8")
            compose_path.write_text(
                "services:\n  web:\n    image: ghcr.io/example/app-web@sha256:dead\n",
                encoding="utf-8",
            )
            result = run_deploy(
                ["deploy", "web", VALID_DIGEST],
                services_path=services_path,
                compose_runner=lambda argv: 0,
                health_checker=lambda url: True,
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.status, "ERROR")
            self.assertIn("WEB_IMAGE_DIGEST", result.message)

    def test_compose_digest_var_only_in_comment_rejected(self):
        """digest_var in a comment without image@${digest_var} pin is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path, env_path, compose_path, _ = _prepare_deploy_tmp(tmp_path)
            env_path.write_text(f"WEB_IMAGE_DIGEST={PREV_DIGEST}\n", encoding="utf-8")
            compose_path.write_text(
                "# WEB_IMAGE_DIGEST must be set elsewhere\n"
                "services:\n  web:\n    image: ghcr.io/example/app-web\n",
                encoding="utf-8",
            )
            result = run_deploy(
                ["deploy", "web", VALID_DIGEST],
                services_path=services_path,
                compose_runner=lambda argv: 0,
                health_checker=lambda url: True,
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.status, "ERROR")
            msg = result.message.lower()
            self.assertTrue(
                "pin" in msg or "digest" in msg or "@$" in result.message,
                result.message,
            )

    def test_compose_full_pin_token_only_in_comment_rejected(self):
        """Full pin token only in a comment + image:repo:stable must be rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path, env_path, compose_path, services = _prepare_deploy_tmp(
                tmp_path
            )
            env_path.write_text(f"WEB_IMAGE_DIGEST={PREV_DIGEST}\n", encoding="utf-8")
            image = services["services"]["web"]["image"]
            digest_var = services["services"]["web"]["digest_var"]
            pin = f"{image}@${{{digest_var}}}"
            compose_path.write_text(
                f"# image: {pin}\nservices:\n  web:\n    image: {image}:stable\n",
                encoding="utf-8",
            )
            result = run_deploy(
                ["deploy", "web", VALID_DIGEST],
                services_path=services_path,
                compose_runner=lambda argv: 0,
                health_checker=lambda url: True,
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.status, "ERROR")
            msg = result.message.lower()
            self.assertTrue(
                "pin" in msg or "digest" in msg or "@$" in result.message,
                result.message,
            )

    def test_compose_allowlisted_image_digest_pin_accepted(self):
        """Happy path: allowlisted_image@${digest_var} in compose text."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path, env_path, compose_path, services = _prepare_deploy_tmp(
                tmp_path
            )
            env_path.write_text(f"WEB_IMAGE_DIGEST={PREV_DIGEST}\n", encoding="utf-8")
            image = services["services"]["web"]["image"]
            digest_var = services["services"]["web"]["digest_var"]
            self.assertIn(f"{image}@${{{digest_var}}}", compose_path.read_text())
            result = run_deploy(
                ["deploy", "web", VALID_DIGEST],
                services_path=services_path,
                compose_runner=lambda argv: 0,
                health_checker=lambda url: True,
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.status, "PASS")


class ClientVmFilesTests(unittest.TestCase):
    def test_required_files_exist(self):
        for path in (NEXUS_DEPLOY, INSTALL_SH, README):
            self.assertTrue(path.is_file(), f"missing required file: {path}")

    def test_installer_creates_restricted_user_and_command(self):
        text = INSTALL_SH.read_text(encoding="utf-8")
        self.assertIn("nexus-deploy", text)
        self.assertTrue("useradd" in text or "adduser" in text)
        self.assertIn("/usr/sbin/nologin", text)
        self.assertIn("authorized_keys", text)
        self.assertIn("command=", text)
        self.assertIn("/usr/local/bin/nexus-deploy", text)
        # No client hostnames / IPs / live keys in the installer.
        self.assertIsNone(re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text))
        self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", text)
        self.assertNotIn("ssh-rsa AAAA", text)

    def test_nexus_deploy_entrypoint_is_executable_script(self):
        text = NEXUS_DEPLOY.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!"))
        # Never evaluate user strings via the eval builtin.
        self.assertNotRegex(text, r"(?m)^\s*eval\b")
        self.assertIn("deploy", text)


if __name__ == "__main__":
    unittest.main()
