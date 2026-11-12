import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_marketplace_skills.py"
SPEC = importlib.util.spec_from_file_location("validate_marketplace_skills", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


class MarketplaceSkillTests(unittest.TestCase):
    def test_public_candidates_follow_marketplace_contract(self):
        candidates = sorted((ROOT / "marketplace" / "agensi").glob("**/SKILL.md"))
        self.assertTrue(candidates)
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertEqual(validator.validate(candidate), [])

    def test_private_paths_and_project_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "SKILL.md"
            fixture.write_text(
                "---\n"
                "name: Unsafe\n"
                "description: Does a job.\n"
                "summary: Unsafe fixture\n"
                "version: 0.1.0\n"
                "tags:\n  - test\n"
                "keywords:\n  - test\n"
                "use_cases:\n  - test\n"
                "docs_url: https://example.test\n"
                "---\n"
                "Requires: PuKnowledge MCP\n"
                "## Workflow\n/Users/example/private\nC:\\Users\\example\\private.txt\n"
                "## Output contract\n"
                "## Safety and privacy\nowner-private-project\n"
                "## Known limitations\n",
                encoding="utf-8",
            )
            errors = validator.validate(fixture)
        self.assertIn("contains absolute macOS user path", errors)
        self.assertIn("contains absolute Windows user path", errors)
        self.assertIn("contains private project identifier", errors)

    def test_local_private_denylist_is_not_baked_into_public_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "SKILL.md"
            source = ROOT / "marketplace" / "agensi" / "project-continuity" / "SKILL.md"
            fixture.write_text(
                source.read_text(encoding="utf-8") + "\nLocal secret codename: Example-Zeta\n",
                encoding="utf-8",
            )
            errors = validator.validate(fixture, ("Example-Zeta",))
        self.assertIn("contains a term from the local private denylist", errors)


if __name__ == "__main__":
    unittest.main()
