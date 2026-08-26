import json
import unittest
from pathlib import Path

from nexus_harness.affected import AffectedPlan
from nexus_harness.build import (
    build_affected_images,
    image_ref_for,
    plan_image_builds,
)
from nexus_harness.deploy_manifest import DeployManifest, assemble_deploy_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "core" / "ci" / "deploy-manifest.schema.json"
EXAMPLE_REPO = "Rubens-Marques/SDR-Plataform"
COMMIT = "9e6f3ccc19dee64c03e771c87a01679d4ab9a98e"
VALID_DIGEST = "sha256:" + ("a" * 64)


class BuildTests(unittest.TestCase):
    def test_manifest_rejects_latest_tag(self):
        with self.assertRaises(ValueError):
            DeployManifest(service="web", image="ghcr.io/acme/web:latest", digest="")

    def test_manifest_rejects_empty_digest(self):
        with self.assertRaises(ValueError):
            DeployManifest(
                service="web",
                image="ghcr.io/acme/web",
                digest="",
            )

    def test_manifest_rejects_mutable_tag_as_identity(self):
        with self.assertRaises(ValueError):
            DeployManifest(
                service="web",
                image="ghcr.io/acme/web:main",
                digest=VALID_DIGEST,
            )
        with self.assertRaises(ValueError):
            DeployManifest(
                service="web",
                image="ghcr.io/acme/web",
                digest="latest",
            )

    def test_manifest_accepts_digest_identity(self):
        artifact = DeployManifest(
            service="web",
            image="ghcr.io/rubens-marques/sdr-plataform-web",
            digest=VALID_DIGEST,
        )
        self.assertEqual(artifact.service, "web")
        self.assertEqual(artifact.digest, VALID_DIGEST)
        self.assertNotIn(":", artifact.image.split("/")[-1])

    def test_assemble_manifest_binds_repository_commit_artifacts(self):
        artifact = DeployManifest(
            service="web",
            image="ghcr.io/rubens-marques/sdr-plataform-web",
            digest=VALID_DIGEST,
        )
        document = assemble_deploy_manifest(
            repository=EXAMPLE_REPO,
            commit=COMMIT,
            artifacts=(artifact,),
        )
        self.assertEqual(document["repository"], EXAMPLE_REPO)
        self.assertEqual(document["commit"], COMMIT)
        self.assertEqual(len(document["artifacts"]), 1)
        self.assertEqual(document["artifacts"][0]["service"], "web")
        self.assertEqual(document["artifacts"][0]["digest"], VALID_DIGEST)
        self.assertEqual(
            document["artifacts"][0]["image"],
            "ghcr.io/rubens-marques/sdr-plataform-web",
        )

    def test_schema_requires_digest_and_forbids_extra_keys(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            set(schema["required"]),
            {"repository", "commit", "artifacts"},
        )
        self.assertFalse(schema["additionalProperties"])
        artifact = schema["$defs"]["artifact"]
        self.assertEqual(
            set(artifact["required"]),
            {"service", "image", "digest"},
        )
        self.assertFalse(artifact["additionalProperties"])
        digest_schema = artifact["properties"]["digest"]
        self.assertIn("sha256:", digest_schema.get("pattern", ""))

    def test_plan_only_builds_affected_images(self):
        affected = AffectedPlan(
            components=("web",),
            checks=("vitest-web",),
            images=("web",),
        )
        plan = plan_image_builds(
            affected.images,
            repository=EXAMPLE_REPO,
            commit=COMMIT,
        )
        self.assertEqual([item.service for item in plan], ["web"])
        self.assertNotIn("server", [item.service for item in plan])
        self.assertNotIn("figma-worker", [item.service for item in plan])

    def test_buildkit_command_is_deterministic_with_scoped_cache(self):
        plan = plan_image_builds(
            ("web", "server"),
            repository=EXAMPLE_REPO,
            commit=COMMIT,
        )
        self.assertEqual(len(plan), 2)
        web = plan[0]
        self.assertEqual(web.service, "web")
        self.assertEqual(
            web.image,
            "ghcr.io/rubens-marques/sdr-plataform-web",
        )
        self.assertEqual(web.human_tag, COMMIT)
        argv = list(web.build_argv)
        self.assertEqual(argv[0:3], ["docker", "buildx", "build"])
        cache_from = (
            "type=registry,ref=ghcr.io/rubens-marques/sdr-plataform-web:buildcache"
        )
        cache_to = (
            "type=registry,ref=ghcr.io/rubens-marques/sdr-plataform-web:buildcache,"
            "mode=max"
        )
        self.assertIn(f"--cache-from={cache_from}", argv)
        self.assertIn(f"--cache-to={cache_to}", argv)
        self.assertIn(
            f"--tag=ghcr.io/rubens-marques/sdr-plataform-web:{COMMIT}",
            argv,
        )
        self.assertIn("--push", argv)
        server = plan[1]
        self.assertIn(
            "ghcr.io/rubens-marques/sdr-plataform-server:buildcache",
            " ".join(server.build_argv),
        )
        self.assertNotIn(
            "sdr-plataform-web:buildcache",
            " ".join(server.build_argv),
        )

    def test_image_ref_for_is_deterministic(self):
        self.assertEqual(
            image_ref_for(EXAMPLE_REPO, "web"),
            "ghcr.io/rubens-marques/sdr-plataform-web",
        )
        self.assertEqual(
            image_ref_for(EXAMPLE_REPO, "figma-worker"),
            "ghcr.io/rubens-marques/sdr-plataform-figma-worker",
        )

    def test_build_records_registry_digest_via_injected_runner(self):
        digests = {
            "ghcr.io/rubens-marques/sdr-plataform-web": "sha256:" + ("b" * 64),
            "ghcr.io/rubens-marques/sdr-plataform-server": "sha256:" + ("c" * 64),
        }
        calls: list[tuple[str, ...]] = []

        def fake_runner(argv, *, cwd=None):
            calls.append(tuple(argv))
            joined = " ".join(argv)
            if "buildx" in argv and "build" in argv:
                return 0, "", ""
            if "imagetools" in argv and "inspect" in argv:
                for image, digest in digests.items():
                    if image in joined:
                        return 0, digest + "\n", ""
                return 1, "", "unknown image"
            return 1, "", f"unexpected: {joined}"

        affected = AffectedPlan(
            components=("web", "server"),
            checks=(),
            images=("web", "server"),
        )
        manifest = build_affected_images(
            affected.images,
            repository=EXAMPLE_REPO,
            commit=COMMIT,
            runner=fake_runner,
        )
        self.assertEqual(manifest["repository"], EXAMPLE_REPO)
        self.assertEqual(manifest["commit"], COMMIT)
        by_service = {item["service"]: item for item in manifest["artifacts"]}
        self.assertEqual(set(by_service), {"web", "server"})
        self.assertEqual(
            by_service["web"]["digest"], digests[by_service["web"]["image"]]
        )
        self.assertEqual(
            by_service["server"]["digest"],
            digests[by_service["server"]["image"]],
        )
        self.assertNotIn("latest", json.dumps(manifest))
        # One build/push per image; inspect resolves digest — no second push.
        build_calls = [c for c in calls if "build" in c and "buildx" in c]
        inspect_calls = [c for c in calls if "imagetools" in c]
        self.assertEqual(len(build_calls), 2)
        self.assertEqual(len(inspect_calls), 2)
        for call in build_calls:
            self.assertEqual(call.count("--push"), 1)

    def test_empty_affected_images_yields_empty_artifacts(self):
        manifest = build_affected_images(
            (),
            repository=EXAMPLE_REPO,
            commit=COMMIT,
            runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no runner")),
        )
        self.assertEqual(manifest["artifacts"], [])


if __name__ == "__main__":
    unittest.main()
