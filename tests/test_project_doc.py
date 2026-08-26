import unittest
from pathlib import Path

from nexus_harness.project import ProjectRegistry
from nexus_harness.project_doc import generate_project_doc, render_project_doc


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "PROJECT.md"

SECTIONS = (
    "Identity",
    "GitHub",
    "Current Focus",
    "Runtime Profile",
    "Quality",
    "Observability",
    "Commands",
    "Architecture links",
)

# Documentation-only fixtures. Must never appear in generated Markdown.
UNSAFE = {
    "token": "ghp_AAAAAAAAAAAAAAAAAAAA",
    "vm_ip": "203.0.113.10",
    "vm_ip6": "2001:db8::10",
    "ssh": "ssh deploy@203.0.113.10",
    "key": "-----BEGIN OPENSSH PRIVATE KEY-----",
    "home": "/Users/someone/Projects/secret",
}


def _registry():
    return ProjectRegistry.from_dict(
        {
            "projects": {
                "sdr-platform": {
                    "name": "SDR Platform",
                    "repository": "Rubens-Marques/SDR-Plataform",
                    "client": "vuca",
                    "status": "active",
                }
            }
        }
    )


def _profile(**extra):
    payload = {
        "profile": {"name": "default", "quality_profile": "standard"},
        "runtime": {
            "prefer_local_execution": True,
            "ci_compute": "self_hosted",
            "production_access": "never_implicit",
        },
        "checks": {
            "format_lint": "biome",
            "unit_integration": "vitest",
            "e2e_visual": "playwright",
            "security": "trivy",
        },
        "observability": {"id": "sdr-platform"},
        "architecture": {"links": ["docs/ARCHITECTURE.md"]},
    }
    payload.update(extra)
    return payload


class ProjectDocTests(unittest.TestCase):
    def test_template_exists(self):
        self.assertTrue(TEMPLATE.is_file())
        text = TEMPLATE.read_text(encoding="utf-8")
        for heading in SECTIONS:
            self.assertIn(f"## {heading}", text)

    def test_generated_doc_includes_identity_from_registry(self):
        project = _registry().by_id("sdr-platform")
        markdown = render_project_doc(project, _profile())
        self.assertIn("sdr-platform", markdown)
        self.assertIn("SDR Platform", markdown)
        self.assertIn("Rubens-Marques/SDR-Plataform", markdown)
        self.assertIn("vuca", markdown)
        self.assertIn("active", markdown)

    def test_generated_doc_has_required_sections(self):
        project = _registry().by_id("sdr-platform")
        markdown = render_project_doc(project, _profile())
        for heading in SECTIONS:
            self.assertIn(f"## {heading}", markdown)

    def test_generated_doc_includes_quality_commands_and_observability(self):
        project = _registry().by_id("sdr-platform")
        markdown = render_project_doc(project, _profile())
        self.assertIn("standard", markdown)
        self.assertIn("biome", markdown)
        self.assertIn("vitest", markdown)
        self.assertIn("playwright", markdown)
        self.assertIn("trivy", markdown)
        self.assertRegex(
            markdown, r"(?im)^\s*[-*].*sdr-platform|Observability[\s\S]*sdr-platform"
        )

    def test_generate_project_doc_reuses_registry_record(self):
        registry = _registry()
        markdown = generate_project_doc(
            "sdr-platform",
            registry=registry,
            profile=_profile(),
        )
        project = registry.by_id("sdr-platform")
        self.assertIn(project.id, markdown)
        self.assertIn(project.repository, markdown)
        self.assertIn(project.client, markdown)
        self.assertIn(project.status, markdown)

    def test_generate_uses_seed_registry_and_default_profile(self):
        markdown = generate_project_doc(
            "sdr-platform",
            registry=ProjectRegistry.from_path(ROOT / "projects.toml"),
        )
        self.assertIn("sdr-platform", markdown)
        self.assertIn("Rubens-Marques/SDR-Plataform", markdown)
        self.assertIn("vuca", markdown)
        self.assertIn("active", markdown)
        self.assertIn("standard", markdown)

    def test_current_focus_from_open_epic(self):
        project = _registry().by_id("sdr-platform")
        markdown = render_project_doc(
            project,
            _profile(),
            current_focus="Epic #12 — Checkout redesign",
        )
        self.assertIn("Epic #12 — Checkout redesign", markdown)

    def test_generated_doc_excludes_secrets_ips_ssh_and_private_paths(self):
        project = _registry().by_id("sdr-platform")
        profile = _profile(
            token=UNSAFE["token"],
            vm_ip=UNSAFE["vm_ip"],
            ssh_target=UNSAFE["ssh"],
            private_key=UNSAFE["key"],
            machine_path=UNSAFE["home"],
        )
        profile["architecture"] = {"links": [UNSAFE["home"], "docs/ARCHITECTURE.md"]}
        profile["observability"] = {"id": UNSAFE["token"]}
        markdown = render_project_doc(
            project,
            profile,
            current_focus=f"Ship to {UNSAFE['vm_ip']} {UNSAFE['vm_ip6']} via {UNSAFE['ssh']}",
        )
        for value in UNSAFE.values():
            self.assertNotIn(value, markdown)
        self.assertIn("docs/ARCHITECTURE.md", markdown)
        self.assertIn("sdr-platform", markdown)

    def test_unknown_project_id_rejected(self):
        with self.assertRaises(ValueError):
            generate_project_doc("missing", registry=_registry(), profile=_profile())

    def test_render_is_deterministic(self):
        project = _registry().by_id("sdr-platform")
        profile = _profile()
        self.assertEqual(
            render_project_doc(project, profile, current_focus="Feature #9"),
            render_project_doc(project, profile, current_focus="Feature #9"),
        )
