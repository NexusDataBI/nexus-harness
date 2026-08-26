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


class DeployRollbackTests(unittest.TestCase):
    def test_rollback_when_health_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path = tmp_path / "services.json"
            env_path = tmp_path / ".env"
            evidence_path = tmp_path / "rollback.json"
            services = _services_payload()
            services["services"]["web"]["env_file"] = str(env_path)
            services["services"]["web"]["compose_file"] = str(tmp_path / "compose.yml")
            services["services"]["web"]["project_dir"] = str(tmp_path)
            services_path.write_text(json.dumps(services), encoding="utf-8")
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

    def test_successful_deploy_requires_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            services_path = tmp_path / "services.json"
            env_path = tmp_path / ".env"
            services = _services_payload()
            services["services"]["web"]["env_file"] = str(env_path)
            services["services"]["web"]["compose_file"] = str(tmp_path / "compose.yml")
            services["services"]["web"]["project_dir"] = str(tmp_path)
            services_path.write_text(json.dumps(services), encoding="utf-8")
            env_path.write_text(f"WEB_IMAGE_DIGEST={PREV_DIGEST}\n", encoding="utf-8")

            result = run_deploy(
                ["deploy", "web", VALID_DIGEST],
                services_path=services_path,
                compose_runner=lambda argv: 0,
                health_checker=lambda url: True,
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.status, "PASS")
            self.assertIn(VALID_DIGEST, env_path.read_text(encoding="utf-8"))


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
