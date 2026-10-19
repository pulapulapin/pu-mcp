"""Contracts for the public base + on-demand extension model."""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from extension_registry import BASE, PUBLIC_MODULES, describe_modules  # noqa: E402
from module_server import resolve_modules  # noqa: E402


class ExtensionArchitectureTests(unittest.TestCase):
    def test_core_is_the_only_mandatory_base(self):
        description = describe_modules(('core', 'fs', 'longform'))
        self.assertEqual(description['model'], 'base_plus_extensions')
        self.assertEqual(description['base']['module_id'], 'core')
        self.assertEqual(description['base']['layer'], 'base')
        self.assertEqual(description['base']['depends_on'], [])
        self.assertEqual(
            {item['module_id'] for item in description['extensions']},
            {'fs', 'longform'},
        )

    def test_public_distribution_only_exposes_generic_extensions(self):
        self.assertEqual(PUBLIC_MODULES, ('core', 'fs', 'longform'))
        self.assertEqual(resolve_modules(preset='owner'), PUBLIC_MODULES)
        self.assertEqual(resolve_modules(preset='full'), PUBLIC_MODULES)
        self.assertEqual(BASE.module_id, 'core')


if __name__ == '__main__':
    unittest.main()
