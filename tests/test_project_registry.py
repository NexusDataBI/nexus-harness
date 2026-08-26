import tempfile
import unittest
from pathlib import Path

from nexus_harness.project import ProjectRegistry


ROOT = Path(__file__).resolve().parents[1]


def _project(
    repository="Rubens-Marques/SDR-Plataform",
    client="vuca",
    status="active",
    **extra,
):
    payload = {"repository": repository, "client": client, "status": status}
    payload.update(extra)
    return payload


class ProjectRegistryTests(unittest.TestCase):
    def test_repository_resolves_project(self):
        registry = ProjectRegistry.from_dict(
            {
                "projects": {
                    "sdr-platform": {
                        "repository": "Rubens-Marques/SDR-Plataform",
                        "client": "vuca",
                        "status": "active",
                    }
                }
            }
        )
        project = registry.by_repository("Rubens-Marques/SDR-Plataform")
        self.assertEqual(project.id, "sdr-platform")

    def test_by_id_resolves_project(self):
        registry = ProjectRegistry.from_dict(
            {"projects": {"sdr-platform": _project(name="SDR Platform")}}
        )
        project = registry.by_id("sdr-platform")
        self.assertEqual(project.repository, "Rubens-Marques/SDR-Plataform")
        self.assertEqual(project.client, "vuca")
        self.assertEqual(project.status, "active")
        self.assertEqual(project.name, "SDR Platform")

    def test_project_record_is_immutable(self):
        registry = ProjectRegistry.from_dict({"projects": {"sdr-platform": _project()}})
        project = registry.by_id("sdr-platform")
        with self.assertRaises(AttributeError):
            project.client = "other"

    def test_github_https_url_normalizes_to_same_project(self):
        registry = ProjectRegistry.from_dict({"projects": {"sdr-platform": _project()}})
        project = registry.by_repository(
            "https://github.com/Rubens-Marques/SDR-Plataform"
        )
        self.assertEqual(project.id, "sdr-platform")

    def test_github_git_suffix_normalizes_to_same_project(self):
        registry = ProjectRegistry.from_dict({"projects": {"sdr-platform": _project()}})
        project = registry.by_repository(
            "https://github.com/Rubens-Marques/SDR-Plataform.git"
        )
        self.assertEqual(project.id, "sdr-platform")

    def test_unrelated_repositories_do_not_resolve(self):
        registry = ProjectRegistry.from_dict({"projects": {"sdr-platform": _project()}})
        unrelated = (
            "Rubens-Marques/SDR-Plataform-other",
            "other/SDR-Plataform",
            "https://gitlab.com/Rubens-Marques/SDR-Plataform",
            "https://github.com.evil.com/Rubens-Marques/SDR-Plataform",
            "https://github.com/Rubens-Marques/SDR-Plataform/tree/main",
            "git@github.com:Rubens-Marques/SDR-Plataform.git",
            "https://user:token@github.com/Rubens-Marques/SDR-Plataform",
        )
        for repository in unrelated:
            with self.subTest(repository=repository):
                with self.assertRaises(ValueError):
                    registry.by_repository(repository)

    def test_duplicate_repository_rejected(self):
        with self.assertRaises(ValueError):
            ProjectRegistry.from_dict(
                {
                    "projects": {
                        "sdr-platform": _project(),
                        "alias": _project(),
                    }
                }
            )

    def test_duplicate_normalized_repository_rejected(self):
        with self.assertRaises(ValueError):
            ProjectRegistry.from_dict(
                {
                    "projects": {
                        "sdr-platform": _project(),
                        "alias": _project(
                            repository="https://github.com/Rubens-Marques/SDR-Plataform.git"
                        ),
                    }
                }
            )

    def test_duplicate_id_rejected(self):
        with self.assertRaises(ValueError):
            ProjectRegistry.from_dict(
                {
                    "projects": {
                        "sdr-platform": _project(),
                        "marketing-hub": _project(
                            id="sdr-platform",
                            repository="NexusDataBI/marketing-hub",
                            client="nexus",
                        ),
                    }
                }
            )

    def test_missing_required_fields_rejected(self):
        for field in ("repository", "client", "status"):
            project = _project()
            del project[field]
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    ProjectRegistry.from_dict({"projects": {"sdr-platform": project}})

    def test_blank_required_fields_rejected(self):
        for field in ("repository", "client", "status"):
            project = _project()
            project[field] = "   "
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    ProjectRegistry.from_dict({"projects": {"sdr-platform": project}})

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            ProjectRegistry.from_dict(
                {"projects": {"sdr-platform": _project(status="unknown")}}
            )

    def test_paused_and_archived_status_accepted(self):
        registry = ProjectRegistry.from_dict(
            {
                "projects": {
                    "paused-app": _project(
                        repository="acme/paused-app",
                        client="acme",
                        status="paused",
                    ),
                    "archived-app": _project(
                        repository="acme/archived-app",
                        client="acme",
                        status="archived",
                    ),
                }
            }
        )
        self.assertEqual(registry.by_id("paused-app").status, "paused")
        self.assertEqual(registry.by_id("archived-app").status, "archived")

    def test_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):
            ProjectRegistry.from_dict(
                {"projects": {"sdr-platform": _project(token="should-not-be-here")}}
            )

    def test_loads_from_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "projects.toml"
            path.write_text(
                "\n".join(
                    [
                        "[projects.sdr-platform]",
                        'name = "SDR Platform"',
                        'repository = "Rubens-Marques/SDR-Plataform"',
                        'client = "vuca"',
                        'status = "active"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            registry = ProjectRegistry.from_path(path)
            project = registry.by_id("sdr-platform")
            self.assertEqual(project.name, "SDR Platform")
            self.assertEqual(
                registry.by_repository(
                    "https://github.com/Rubens-Marques/SDR-Plataform.git"
                ).id,
                "sdr-platform",
            )

    def test_loads_seed_projects_toml(self):
        registry = ProjectRegistry.from_path(ROOT / "projects.toml")
        sdr = registry.by_id("sdr-platform")
        hub = registry.by_id("marketing-hub")
        self.assertEqual(sdr.name, "SDR Platform")
        self.assertEqual(sdr.repository, "Rubens-Marques/SDR-Plataform")
        self.assertEqual(sdr.client, "vuca")
        self.assertEqual(sdr.status, "active")
        self.assertEqual(hub.name, "Marketing Hub")
        self.assertEqual(hub.repository, "NexusDataBI/marketing-hub")
        self.assertEqual(hub.client, "nexus")
        self.assertEqual(hub.status, "active")
        self.assertIs(
            registry.by_repository("NexusDataBI/marketing-hub"),
            hub,
        )
