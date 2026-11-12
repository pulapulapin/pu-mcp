import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "package_marketplace_skill.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("package_marketplace_skill", MODULE_PATH)
packager = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(packager)


class MarketplacePackageTests(unittest.TestCase):
    def test_package_is_deterministic_and_contains_only_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            first_report = packager.build(first)
            second_report = packager.build(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_report["sha256"], second_report["sha256"])
            self.assertFalse(first_report["submitted"])
            self.assertFalse(first_report["published"])
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["puknowledge-project-continuity-starter/SKILL.md"],
                )
                self.assertEqual(
                    archive.read("puknowledge-project-continuity-starter/SKILL.md"),
                    (
                        ROOT
                        / "marketplace"
                        / "agensi"
                        / "project-continuity"
                        / "SKILL.md"
                    ).read_bytes(),
                )

    def test_private_denylist_blocks_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "blocked.zip"
            with self.assertRaisesRegex(ValueError, "local private denylist"):
                packager.build(output, ("PuKnowledge Project Continuity Starter",))
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
