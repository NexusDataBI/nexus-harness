import tempfile
import unittest
from pathlib import Path

from nexus_harness.config import load_toml


class ConfigTests(unittest.TestCase):
    def test_load_toml_returns_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.toml"
            path.write_text("[workflow]\nmandatory = true\n", encoding="utf-8")
            data = load_toml(path)
            self.assertTrue(data["workflow"]["mandatory"])
