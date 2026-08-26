import json
import re
import unittest
from pathlib import Path

from nexus_harness.affected import AffectedPlan, load_ci_profile
from nexus_harness.build import (
    build_affected_images,
    image_ref_for,
    image_specs_from_profile,
    plan_image_builds,
)
from nexus_harness.deploy_manifest import DeployManifest, assemble_deploy_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "core" / "ci" / "deploy-manifest.schema.json"
SDR_PROFILE = REPO_ROOT / "profiles" / "projects" / "sdr-platform.toml"
EXAMPLE_REPO = "Rubens-Marques/SDR-Plataform"
COMMIT = "9e6f3ccc19dee64c03e771c87a01679d4ab9a98e"
VALID_DIGEST = "sha256:" + ("a" * 64)

# Explicit mapping for unit tests (no core hardcoded SDR defaults).
TEST_SPECS = {
    "web": {"dockerfile": "apps/web/Dockerfile", "context": "."},
    "server": {"dockerfile": "apps/server/Dockerfile", "context": "."},
    "figma-worker": {
        "dockerfile": "apps/server/Dockerfile.figma-worker",
        "context": ".",
    },
}


def _schema_rejects(payload: dict) -> bool:
    """True if payload violates deploy-manifest.schema.json documented constraints.

    Uses the schema file's patterns/required/additionalProperties — stdlib only,
    no jsonschema dependency. Keep patterns in the schema accurate.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return True
    if schema.get("additionalProperties") is False:
        allowed = set(schema.get("properties", {}))
        if set(payload) - allowed:
            return True
    for key in schema.get("required", []):
        if key not in payload:
            return True
    for key, prop in schema.get("properties", {}).items():
        if key not in payload:
            continue
        value = payload[key]
        if prop.get("type") == "string" and not isinstance(value, str):
            return True
        if prop.get("type") == "string" and prop.get("minLength"):
            if len(value) < int(prop["minLength"]):
                return True
        if prop.get("type") == "array" and not isinstance(value, list):
            return True
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return True
    artifact_schema = schema["$defs"]["artifact"]
    image_pat = re.compile(artifact_schema["properties"]["image"]["pattern"])
    digest_pat = re.compile(artifact_schema["properties"]["digest"]["pattern"])
    required_art = set(artifact_schema.get("required", []))
    allow_extra = artifact_schema.get("additionalProperties", True)
    for item in artifacts:
        if not isinstance(item, dict):
            return True
        if allow_extra is False and set(item) - set(
            artifact_schema.get("properties", {})
        ):
            return True
        if required_art - set(item):
            return True
        image = item.get("image", "")
        digest = item.get("digest", "")
        if not isinstance(image, str) or not image_pat.fullmatch(image):
            return True
        if not isinstance(digest, str) or not digest_pat.fullmatch(digest):
            return True
        service = item.get("service", "")
        if not isinstance(service, str) or not service:
            return True
    return False


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
        image_schema = artifact["properties"]["image"]
        image_pat = image_schema.get("pattern", "")
        self.assertTrue(image_pat, "image must have a pattern forbidding tag/digest")
        self.assertRegex("ghcr.io/acme/web", image_pat)
        self.assertIsNone(re.fullmatch(image_pat, "ghcr.io/acme/web:latest"))
        self.assertIsNone(
            re.fullmatch(image_pat, "ghcr.io/acme/web@sha256:" + ("a" * 64))
        )

    def test_schema_rejects_image_with_latest_tag(self):
        payload = {
            "repository": EXAMPLE_REPO,
            "commit": COMMIT,
            "artifacts": [
                {
                    "service": "web",
                    "image": "ghcr.io/acme/web:latest",
                    "digest": VALID_DIGEST,
                }
            ],
        }
        self.assertTrue(_schema_rejects(payload))

    def test_schema_rejects_empty_digest(self):
        payload = {
            "repository": EXAMPLE_REPO,
            "commit": COMMIT,
            "artifacts": [
                {
                    "service": "web",
                    "image": "ghcr.io/acme/web",
                    "digest": "",
                }
            ],
        }
        self.assertTrue(_schema_rejects(payload))

    def test_schema_accepts_valid_manifest(self):
        payload = {
            "repository": EXAMPLE_REPO,
            "commit": COMMIT,
            "artifacts": [
                {
                    "service": "web",
                    "image": "ghcr.io/rubens-marques/sdr-plataform-web",
                    "digest": VALID_DIGEST,
                }
            ],
        }
        self.assertFalse(_schema_rejects(payload))

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
            image_specs=TEST_SPECS,
        )
        self.assertEqual([item.service for item in plan], ["web"])
        self.assertNotIn("server", [item.service for item in plan])
        self.assertNotIn("figma-worker", [item.service for item in plan])

    def test_buildkit_command_is_deterministic_with_scoped_cache(self):
        plan = plan_image_builds(
            ("web", "server"),
            repository=EXAMPLE_REPO,
            commit=COMMIT,
            image_specs=TEST_SPECS,
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
        self.assertTrue(
            any(a.startswith("--metadata-file=") for a in argv),
            "build must capture digest via --metadata-file, not post-push inspect",
        )
        self.assertIn("--push", argv)
        self.assertNotIn("imagetools", argv)
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

    def test_build_records_digest_from_buildx_metadata_file(self):
        digests = {
            "ghcr.io/rubens-marques/sdr-plataform-web": "sha256:" + ("b" * 64),
            "ghcr.io/rubens-marques/sdr-plataform-server": "sha256:" + ("c" * 64),
        }
        calls: list[tuple[str, ...]] = []

        def fake_runner(argv, *, cwd=None):
            calls.append(tuple(argv))
            joined = " ".join(argv)
            if "buildx" in argv and "build" in argv:
                meta_arg = next(
                    (a for a in argv if a.startswith("--metadata-file=")),
                    None,
                )
                self.assertIsNotNone(
                    meta_arg, "build argv must include --metadata-file"
                )
                meta_path = Path(meta_arg.split("=", 1)[1])
                digest = None
                for image, value in digests.items():
                    if f"--tag={image}:" in joined or f"{image}:" in joined:
                        digest = value
                        break
                self.assertIsNotNone(digest, f"unknown image in build: {joined}")
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.write_text(
                    json.dumps({"containerimage.digest": digest}),
                    encoding="utf-8",
                )
                return 0, "", ""
            if "imagetools" in argv:
                return 1, "", "inspect must not be used for digest identity"
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
            image_specs=TEST_SPECS,
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
        # One build/push per image; digest from metadata file — no imagetools inspect.
        build_calls = [c for c in calls if "build" in c and "buildx" in c]
        inspect_calls = [c for c in calls if "imagetools" in c]
        self.assertEqual(len(build_calls), 2)
        self.assertEqual(len(inspect_calls), 0)
        for call in build_calls:
            self.assertEqual(call.count("--push"), 1)
            self.assertTrue(any(a.startswith("--metadata-file=") for a in call))

    def test_empty_affected_images_yields_empty_artifacts(self):
        manifest = build_affected_images(
            (),
            repository=EXAMPLE_REPO,
            commit=COMMIT,
            runner=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no runner")),
            image_specs=TEST_SPECS,
        )
        self.assertEqual(manifest["artifacts"], [])

    def test_unknown_service_without_mapping_fails_closed(self):
        with self.assertRaises(ValueError) as ctx:
            plan_image_builds(
                ("web",),
                repository=EXAMPLE_REPO,
                commit=COMMIT,
                image_specs={},
            )
        self.assertIn("dockerfile", str(ctx.exception).lower())

    def test_sdr_dockerfile_paths_live_in_profile_not_core(self):
        import nexus_harness.build as build_mod

        source = Path(build_mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("_DOCKERFILE_DEFAULTS", source)
        self.assertNotIn("apps/web/Dockerfile", source)
        self.assertNotIn("Dockerfile.figma-worker", source)
        profile = load_ci_profile(SDR_PROFILE)
        specs = image_specs_from_profile(profile)
        self.assertEqual(specs["web"].dockerfile, "apps/web/Dockerfile")
        self.assertEqual(specs["server"].dockerfile, "apps/server/Dockerfile")
        self.assertEqual(
            specs["figma-worker"].dockerfile,
            "apps/server/Dockerfile.figma-worker",
        )
        plan = plan_image_builds(
            ("web", "figma-worker"),
            repository=EXAMPLE_REPO,
            commit=COMMIT,
            image_specs=specs,
        )
        by_svc = {p.service: p for p in plan}
        self.assertEqual(by_svc["web"].dockerfile, "apps/web/Dockerfile")
        self.assertEqual(
            by_svc["figma-worker"].dockerfile,
            "apps/server/Dockerfile.figma-worker",
        )


if __name__ == "__main__":
    unittest.main()
