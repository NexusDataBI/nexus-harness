import json
import unittest
from pathlib import Path

from nexus_harness.security import normalize_trivy


class SecurityTests(unittest.TestCase):
    def test_critical_vulnerability_blocks(self):
        payload = json.loads(Path("tests/fixtures/trivy.json").read_text())
        report = normalize_trivy(payload)
        self.assertEqual(report.gate, "FAIL")
        self.assertEqual(report.counts["critical"], 1)
        self.assertEqual(report.findings[0].id, "CVE-2099-0001")
        self.assertEqual(report.findings[0].target, "package-lock.json")

    def test_high_with_fixed_version_blocks(self):
        report = normalize_trivy(
            {
                "Results": [
                    {
                        "Target": "requirements.txt",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2099-0002",
                                "PkgName": "example",
                                "InstalledVersion": "1.0.0",
                                "FixedVersion": "1.0.1",
                                "Severity": "HIGH",
                            }
                        ],
                    }
                ]
            }
        )
        self.assertEqual(report.gate, "FAIL")
        self.assertEqual(report.counts["high"], 1)
        self.assertEqual(report.findings[0].id, "CVE-2099-0002")
        self.assertEqual(report.findings[0].target, "requirements.txt")

    def test_high_without_fixed_version_does_not_block(self):
        report = normalize_trivy(
            {
                "Results": [
                    {
                        "Target": "requirements.txt",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2099-0003",
                                "PkgName": "example",
                                "InstalledVersion": "1.0.0",
                                "Severity": "HIGH",
                            }
                        ],
                    }
                ]
            }
        )
        self.assertEqual(report.gate, "PASS")
        self.assertEqual(report.counts["high"], 1)
        self.assertEqual(report.findings[0].id, "CVE-2099-0003")
        self.assertFalse(report.findings[0].blocked)

    def test_normalizes_secret_and_preserves_id_and_target(self):
        report = normalize_trivy(
            {
                "Results": [
                    {
                        "Target": "config/app.env",
                        "Secrets": [
                            {
                                "RuleID": "generic-fake-token",
                                "Severity": "HIGH",
                                "Title": "Fake token for tests",
                            }
                        ],
                    }
                ]
            }
        )
        self.assertEqual(len(report.findings), 1)
        finding = report.findings[0]
        self.assertEqual(finding.id, "generic-fake-token")
        self.assertEqual(finding.target, "config/app.env")
        self.assertEqual(finding.kind, "secret")
        self.assertEqual(finding.severity, "HIGH")
        self.assertEqual(report.gate, "PASS")

    def test_high_misconfiguration_with_remediation_blocks(self):
        report = normalize_trivy(
            {
                "Results": [
                    {
                        "Target": "Dockerfile",
                        "Misconfigurations": [
                            {
                                "ID": "DS002",
                                "Severity": "HIGH",
                                "Title": "Image user is root",
                                "Resolution": "Add a USER instruction",
                            }
                        ],
                    }
                ]
            }
        )
        self.assertEqual(report.gate, "FAIL")
        self.assertEqual(report.counts["high"], 1)
        finding = report.findings[0]
        self.assertEqual(finding.id, "DS002")
        self.assertEqual(finding.target, "Dockerfile")
        self.assertEqual(finding.kind, "misconfiguration")
        self.assertEqual(finding.remediation, "Add a USER instruction")
        self.assertTrue(finding.blocked)

    def test_report_to_dict_matches_schema_contract(self):
        payload = json.loads(Path("tests/fixtures/trivy.json").read_text())
        document = normalize_trivy(payload).to_dict()
        schema = json.loads(
            Path("core/security/security-report.schema.json").read_text()
        )
        required = set(schema["required"])
        properties = set(schema["properties"])
        self.assertTrue(required <= set(document))
        self.assertTrue(set(document) <= properties)
        self.assertEqual(document["scanner"], "trivy")
        finding = document["findings"][0]
        self.assertTrue({"id", "severity"} <= set(finding))
        self.assertEqual(finding["id"], "CVE-2099-0001")
        self.assertEqual(finding["target"], "package-lock.json")
        self.assertTrue(finding["blocked"])
