import unittest
from pathlib import Path

from nexus_harness.affected import Component, load_ci_profile, resolve_affected

REPO_ROOT = Path(__file__).resolve().parents[1]
SDR_PROFILE = REPO_ROOT / "profiles" / "projects" / "sdr-platform.toml"


class AffectedTests(unittest.TestCase):
    def test_web_change_does_not_build_server_image(self):
        components = [
            Component("web", ("apps/web/**",), checks=("web-test",), images=("web",)),
            Component(
                "server",
                ("apps/server/**",),
                checks=("server-test",),
                images=("server",),
            ),
        ]
        plan = resolve_affected(["apps/web/src/button.tsx"], components)
        self.assertEqual(plan.images, ("web",))
        self.assertNotIn("server", plan.components)

    def test_design_system_change_affects_web_not_server(self):
        components = [
            Component(
                "design_system",
                ("design-system/**",),
                checks=("biome", "vitest"),
                images=(),
            ),
            Component(
                "web",
                ("apps/web/**",),
                depends_on=("design_system",),
                checks=("vitest-web",),
                images=("web",),
            ),
            Component(
                "server",
                ("apps/server/**",),
                checks=("vitest-server",),
                images=("server",),
            ),
        ]
        plan = resolve_affected(["design-system/src/button.tsx"], components)
        self.assertIn("design_system", plan.components)
        self.assertIn("web", plan.components)
        self.assertNotIn("server", plan.components)
        self.assertEqual(plan.images, ("web",))
        self.assertNotIn("server", plan.images)

    def test_server_only_change_does_not_affect_web(self):
        components = [
            Component("web", ("apps/web/**",), checks=("web-test",), images=("web",)),
            Component(
                "server",
                ("apps/server/**",),
                checks=("server-test",),
                images=("server",),
            ),
        ]
        plan = resolve_affected(["apps/server/src/main.ts"], components)
        self.assertEqual(plan.components, ("server",))
        self.assertEqual(plan.images, ("server",))
        self.assertNotIn("web", plan.components)
        self.assertNotIn("web", plan.images)

    def test_unknown_path_does_not_select_all_components(self):
        components = [
            Component("web", ("apps/web/**",), checks=("web-test",), images=("web",)),
            Component(
                "server",
                ("apps/server/**",),
                checks=("server-test",),
                images=("server",),
            ),
        ]
        plan = resolve_affected(["docs/readme.md"], components)
        self.assertEqual(plan.components, ())
        self.assertEqual(plan.checks, ())
        self.assertEqual(plan.images, ())

    def test_global_critical_path_marks_all_components(self):
        components = [
            Component("web", ("apps/web/**",), checks=("web-test",), images=("web",)),
            Component(
                "server",
                ("apps/server/**",),
                checks=("server-test",),
                images=("server",),
            ),
            Component(
                "figma_worker",
                ("apps/server/Dockerfile.figma-worker",),
                checks=("trivy-source",),
                images=("figma-worker",),
            ),
        ]
        plan = resolve_affected(
            ["package.json"],
            components,
            global_paths=("package.json", "deploy/**"),
        )
        self.assertEqual(set(plan.components), {"web", "server", "figma_worker"})
        self.assertEqual(set(plan.images), {"web", "server", "figma-worker"})

    def test_figma_worker_dockerfile_affects_figma_worker_image(self):
        components = [
            Component(
                "server",
                ("apps/server/**",),
                checks=("server-test",),
                images=("server",),
            ),
            Component(
                "figma_worker",
                (
                    "apps/server/Dockerfile.figma-worker",
                    "apps/server/src/**/figma/**",
                    "apps/server/figma-plugin/**",
                ),
                checks=("trivy-source",),
                images=("figma-worker",),
            ),
        ]
        plan = resolve_affected(
            ["apps/server/Dockerfile.figma-worker"],
            components,
        )
        self.assertIn("figma_worker", plan.components)
        self.assertIn("figma-worker", plan.images)

    def test_load_sdr_platform_profile(self):
        profile = load_ci_profile(SDR_PROFILE)
        names = {c.name for c in profile.components}
        self.assertEqual(profile.project_id, "sdr-platform")
        self.assertEqual(profile.repository, "Rubens-Marques/SDR-Plataform")
        self.assertIn("design_system", names)
        self.assertIn("web", names)
        self.assertIn("server", names)
        self.assertIn("figma_worker", names)

        web = next(c for c in profile.components if c.name == "web")
        self.assertEqual(web.paths, ("apps/web/**",))
        self.assertEqual(web.depends_on, ("design_system",))
        self.assertEqual(web.images, ("web",))

        design = next(c for c in profile.components if c.name == "design_system")
        self.assertEqual(design.paths, ("design-system/**",))
        self.assertEqual(design.images, ())

        figma = next(c for c in profile.components if c.name == "figma_worker")
        self.assertIn("apps/server/Dockerfile.figma-worker", figma.paths)
        self.assertIn("apps/server/src/**/figma/**", figma.paths)
        self.assertIn("apps/server/figma-plugin/**", figma.paths)
        self.assertEqual(figma.images, ("figma-worker",))

        self.assertIn("package.json", profile.global_paths)
        self.assertIn("package-lock.json", profile.global_paths)
        self.assertIn("tsconfig.base.json", profile.global_paths)
        self.assertIn("docker-compose.dev.yml", profile.global_paths)
        self.assertIn("deploy/**", profile.global_paths)

        plan = resolve_affected(
            ["design-system/tokens.css"],
            profile.components,
            global_paths=profile.global_paths,
        )
        self.assertIn("web", plan.components)
        self.assertNotIn("server", plan.components)
        self.assertEqual(plan.images, ("web",))


if __name__ == "__main__":
    unittest.main()
