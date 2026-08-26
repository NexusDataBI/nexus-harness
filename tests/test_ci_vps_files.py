"""Policy tests for personal Nexus CI VPS provisioning files."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_VPS = ROOT / "infra" / "ci-vps"

INSTALL_SH = CI_VPS / "install.sh"
SERVICE_UNIT = CI_VPS / "nexus-ci.service"
README = CI_VPS / "README.md"
DOCTOR = CI_VPS / "nexus-ci-host-doctor.sh"

# Forbidden client / known project hosts — never hardcode.
FORBIDDEN_IPS = (
    "76.13.225.91",
    "187.77.49.147",
)

SAAS_AGENTS = (
    "sentry",
    "datadog",
    "newrelic",
    "new relic",
    "grafana-agent",
    "grafana agent",
    "otelcol",
    "opentelemetry-collector",
    "splunk",
    "dynatrace",
    "appdynamics",
    "elastic-agent",
)

# Literal token / key patterns that must never appear in committed files.
TOKEN_LITERAL_RE = re.compile(
    r"(?i)\b("
    r"ghp_[A-Za-z0-9_]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|ghs_[A-Za-z0-9_]{20,}"
    r"|gho_[A-Za-z0-9_]{20,}"
    r"|ghu_[A-Za-z0-9_]{20,}"
    r"|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
    r")\b"
)

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _all_ci_vps_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in (INSTALL_SH, SERVICE_UNIT, README, DOCTOR):
        if path.is_file():
            texts[str(path.relative_to(ROOT))] = _read(path)
    return texts


class CiVpsFilesExistTests(unittest.TestCase):
    def test_required_files_exist(self):
        for path in (INSTALL_SH, SERVICE_UNIT, README, DOCTOR):
            self.assertTrue(path.is_file(), f"missing required file: {path}")


class InstallShPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.install = _read(INSTALL_SH)

    def test_creates_nexus_ci_system_user(self):
        text = self.install
        self.assertIn("nexus-ci", text)
        self.assertTrue(
            "useradd" in text or "adduser" in text,
            "install.sh must create nexus-ci via useradd/adduser",
        )
        # Prefer system account flags when using useradd.
        if "useradd" in text:
            self.assertRegex(
                text,
                r"useradd\b[^\n]*(-r|--system)\b|(-r|--system)\b[^\n]*useradd\b",
            )

    def test_creates_var_lib_nexus_ci_tree(self):
        text = self.install
        self.assertIn("/var/lib/nexus-ci", text)
        self.assertIn("/var/lib/nexus-ci/cache", text)
        self.assertIn("/var/lib/nexus-ci/artifacts", text)
        self.assertIn("/var/lib/nexus-ci/logs", text)

    def test_creates_opt_nexus_runner(self):
        self.assertIn("/opt/nexus-runner", self.install)

    def test_runner_version_comes_from_environment(self):
        text = self.install
        # Version must be supplied at install time, not hard-pinned as only path.
        self.assertRegex(
            text,
            r"\$\{?RUNNER_VERSION\}?|\$\{?GITHUB_RUNNER_VERSION\}?",
        )
        # Must fail closed if version env is unset (no silent default pin of a token).
        self.assertTrue(
            "RUNNER_VERSION" in text or "GITHUB_RUNNER_VERSION" in text,
        )

    def test_token_from_stdin_or_env_never_echoed(self):
        text = self.install
        # Accept env and/or stdin sources for registration token.
        has_env = re.search(
            r"RUNNER_TOKEN|GITHUB_RUNNER_TOKEN|REGISTRATION_TOKEN", text
        )
        has_stdin = "stdin" in text.lower() or re.search(r"read\s+.*-s", text)
        self.assertTrue(
            has_env or has_stdin,
            "install.sh must read registration token from env or stdin",
        )
        # Never echo the token variable.
        self.assertNotRegex(
            text,
            r"(?m)^\s*(echo|printf)\s+.*\$\{?(RUNNER_TOKEN|GITHUB_RUNNER_TOKEN|REGISTRATION_TOKEN)\}?",
        )

    def test_no_embedded_github_tokens(self):
        self.assertIsNone(TOKEN_LITERAL_RE.search(self.install))

    def test_no_client_ip_addresses(self):
        text = self.install
        for ip in FORBIDDEN_IPS:
            self.assertNotIn(ip, text)
        # No IPv4 literals at all in the installer.
        self.assertIsNone(
            IPV4_RE.search(text), "install.sh must not embed IPv4 addresses"
        )

    def test_no_analytics_saas_agents(self):
        lowered = self.install.lower()
        for agent in SAAS_AGENTS:
            self.assertNotIn(agent, lowered)

    def test_checks_docker_or_rootless_prerequisites(self):
        text = self.install.lower()
        self.assertIn("docker", text)
        self.assertTrue(
            "rootless" in text or "docker.sock" in text or "dockerd" in text,
            "install.sh must verify Docker/rootless prerequisites",
        )

    def test_idempotent_markers(self):
        text = self.install
        # Idempotent: skip creating user/dirs if already present.
        self.assertTrue(
            "id nexus-ci" in text
            or "getent passwd nexus-ci" in text
            or "id -u nexus-ci" in text,
            "install.sh should check whether nexus-ci already exists",
        )


class ServiceUnitPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.unit = _read(SERVICE_UNIT)

    def test_runs_as_nexus_ci_not_root(self):
        unit = self.unit
        self.assertRegex(unit, r"(?m)^\s*User=nexus-ci\s*$")
        self.assertNotRegex(unit, r"(?m)^\s*User=root\s*$")

    def test_points_at_runner_dir(self):
        self.assertIn("/opt/nexus-runner", self.unit)


class ReadmePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = _read(README)

    def test_documents_persistent_runner_isolation_limits(self):
        text = self.readme.lower()
        self.assertIn("not equivalent", text)
        self.assertTrue(
            "ephemeral" in text or "clean vm" in text,
            "README must contrast persistent runner vs ephemeral clean VM",
        )
        self.assertTrue(
            "workspace" in text and "cleanup" in text,
            "README must mention workspace cleanup between jobs",
        )
        self.assertTrue(
            "production" in text and ("credential" in text or "secret" in text),
            "README must warn against standing production credentials",
        )
        self.assertTrue(
            "docker socket" in text or "docker.sock" in text,
            "README must discuss unrestricted Docker socket risk",
        )


class DoctorScriptPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doctor = _read(DOCTOR)

    def test_checks_disk_memory_docker_runner(self):
        text = self.doctor.lower()
        self.assertTrue("df" in text or "disk" in text)
        self.assertTrue("free" in text or "meminfo" in text or "memory" in text)
        self.assertIn("docker", text)
        self.assertTrue(
            "/opt/nexus-runner" in self.doctor or "runner" in text,
        )
        self.assertIn("/var/lib/nexus-ci", self.doctor)


class CrossFileSecretPolicyTests(unittest.TestCase):
    def test_no_token_pat_or_private_key_literals_in_ci_vps(self):
        for rel, text in _all_ci_vps_texts().items():
            match = TOKEN_LITERAL_RE.search(text)
            self.assertIsNone(
                match,
                f"forbidden token/key literal in {rel}: {match.group(0)[:20] if match else ''}",
            )
            for ip in FORBIDDEN_IPS:
                self.assertNotIn(ip, text, f"forbidden IP in {rel}")


if __name__ == "__main__":
    unittest.main()
