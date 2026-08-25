import json
import re
import unittest
from hashlib import sha256
from pathlib import Path

REQUIRED = {
    "nexus-workflow",
    "nexus-quality",
    "nexus-verify",
    "nexus-handoff",
    "nexus-ship",
    "nexus-frontend",
    "accessibility",
}

ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def directory_content_sha256(directory: Path) -> str:
    """SHA-256 of a sorted path+file-digest manifest.

    Files are walked relative to `directory`. AppleDouble (`._*`) path parts
    and `.DS_Store` are skipped. Each included file contributes one UTF-8
    line `{sha256(bytes)}  {posix_relative_path}\\n`. The directory revision
    is the SHA-256 of the concatenated lines.
    """
    lines = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.name == ".DS_Store" or any(
            part.startswith("._") for part in path.parts
        ):
            continue
        rel = path.relative_to(directory).as_posix()
        digest = sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}\n")
    return sha256("".join(lines).encode("utf-8")).hexdigest()


class SkillContractTests(unittest.TestCase):
    def test_canonical_skills_exist_once(self):
        root = ROOT / "skills"
        names = {p.parent.name for p in root.glob("*/SKILL.md")}
        self.assertEqual(names, REQUIRED)

    def test_vendor_lock_parses_with_real_revisions(self):
        lock_path = ROOT / "upstream" / "vendor-lock.json"
        with lock_path.open(encoding="utf-8") as handle:
            lock = json.load(handle)

        self.assertEqual(lock["schema_version"], 1)
        sources = lock["sources"]
        self.assertIsInstance(sources, list)
        self.assertGreater(len(sources), 0)

        for source in sources:
            self.assertIn("id", source)
            self.assertIn("kind", source)
            self.assertTrue(
                "repository" in source or "source_path" in source,
                msg=f"{source.get('id')} missing repository or source_path",
            )
            self.assertEqual(source["revision_kind"], "content_sha256")
            self.assertRegex(source["revision"], HEX64)
            canonical = ROOT / source["canonical_path"]
            self.assertTrue(
                canonical.exists(),
                msg=f"missing canonical_path {source['canonical_path']}",
            )
            self.assertEqual(
                directory_content_sha256(canonical),
                source["revision"],
                msg=f"revision mismatch for {source['id']}",
            )
