from dataclasses import asdict, dataclass, field
from pathlib import Path

from nexus_harness.config import load_toml

_CORE_SECURITY = Path(__file__).resolve().parents[2] / "core" / "security"
_SEVERITY_COUNTS = ("critical", "high", "medium", "low", "info", "unknown")
_KNOWN_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"})


@dataclass
class Finding:
    id: str
    severity: str
    target: str = ""
    kind: str = "vulnerability"
    fixed_version: str | None = None
    remediation: str | None = None
    package: str | None = None
    installed_version: str | None = None
    blocked: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SecurityReport:
    gate: str
    counts: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    scanner: str = "trivy"
    diff_hash: str | None = None

    def to_dict(self) -> dict:
        payload = {
            "gate": self.gate,
            "scanner": self.scanner,
            "counts": dict(self.counts),
            "findings": [
                item.to_dict() if hasattr(item, "to_dict") else item
                for item in self.findings
            ],
        }
        if self.diff_hash is not None:
            payload["diff_hash"] = self.diff_hash
        return payload


def load_security_policy(path: Path | None = None) -> dict:
    return load_toml(path or _CORE_SECURITY / "policy.toml")


def _blank(value) -> bool:
    return value is None or str(value).strip() == ""


def _severity(raw) -> str:
    return str(raw or "UNKNOWN").strip().upper()


def _available_fix(finding: Finding) -> bool:
    return not _blank(finding.fixed_version) or not _blank(finding.remediation)


def _blocks(finding: Finding, policy: dict) -> bool:
    blocking = policy.get("blocking", {})
    if finding.severity == "CRITICAL" and blocking.get(
        "critical_vulnerability_blocks", True
    ):
        return True
    if (
        finding.severity == "HIGH"
        and blocking.get("high_vulnerability_with_available_fix_blocks", True)
        and _available_fix(finding)
    ):
        return True
    if (
        finding.kind == "secret"
        and finding.severity == "HIGH"
        and blocking.get("high_secret_blocks", True)
    ):
        return True
    if finding.severity not in _KNOWN_SEVERITIES:
        return True
    return False


def _from_vulnerability(item: dict, target: str) -> Finding:
    return Finding(
        id=str(item.get("VulnerabilityID") or item.get("ID") or ""),
        severity=_severity(item.get("Severity")),
        target=target,
        kind="vulnerability",
        fixed_version=item.get("FixedVersion") or None,
        remediation=item.get("Resolution") or item.get("Remediation") or None,
        package=item.get("PkgName"),
        installed_version=item.get("InstalledVersion"),
    )


def _from_secret(item: dict, target: str) -> Finding:
    return Finding(
        id=str(item.get("RuleID") or item.get("ID") or ""),
        severity=_severity(item.get("Severity")),
        target=target,
        kind="secret",
        remediation=item.get("Resolution") or item.get("Remediation") or None,
    )


def _from_misconfiguration(item: dict, target: str) -> Finding:
    return Finding(
        id=str(item.get("ID") or item.get("AVDID") or ""),
        severity=_severity(item.get("Severity")),
        target=target,
        kind="misconfiguration",
        fixed_version=item.get("FixedVersion") or None,
        remediation=item.get("Resolution") or item.get("Remediation") or None,
    )


def _fail_closed_report(*, diff_hash: str | None = None) -> SecurityReport:
    return SecurityReport(
        gate="FAIL",
        counts={name: 0 for name in _SEVERITY_COUNTS},
        findings=[],
        diff_hash=diff_hash,
    )


def normalize_trivy(
    payload, policy: dict | None = None, *, diff_hash: str | None = None
) -> SecurityReport:
    policy = policy or load_security_policy()
    if not isinstance(payload, dict):
        return _fail_closed_report(diff_hash=diff_hash)
    findings: list[Finding] = []
    malformed = False
    results = payload.get("Results") or []
    if not isinstance(results, list):
        return _fail_closed_report(diff_hash=diff_hash)
    for result in results:
        if not isinstance(result, dict):
            malformed = True
            continue
        target = str(result.get("Target") or "")
        for vuln in result.get("Vulnerabilities") or []:
            if not isinstance(vuln, dict):
                malformed = True
                continue
            findings.append(_from_vulnerability(vuln, target))
        for secret in result.get("Secrets") or []:
            if not isinstance(secret, dict):
                malformed = True
                continue
            findings.append(_from_secret(secret, target))
        for misconf in result.get("Misconfigurations") or []:
            if not isinstance(misconf, dict):
                malformed = True
                continue
            findings.append(_from_misconfiguration(misconf, target))

    counts = {name: 0 for name in _SEVERITY_COUNTS}
    blocked = malformed
    for finding in findings:
        key = finding.severity.lower()
        if key in counts:
            counts[key] += 1
        else:
            counts["unknown"] += 1
        finding.blocked = _blocks(finding, policy)
        blocked = blocked or finding.blocked

    return SecurityReport(
        gate="FAIL" if blocked else "PASS",
        counts=counts,
        findings=findings,
        diff_hash=diff_hash,
    )
