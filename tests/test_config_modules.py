"""Neutral config: modules + capture keys with legacy aliases."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from novel_config import load_settings


class ConfigModulesTests(unittest.TestCase):
    def test_capture_alias_and_modules_list(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = root / 'config.json'
            cfg.write_text(json.dumps({
                'data_dir': str(root / 'data'),
                'workspaces': {'sample': {'path': str(root), 'label': 'Sample', 'domain': 'research'}},
                'modules': ['core', 'fs'],
                'capture': {'enabled': False},
            }), encoding='utf-8')
            with patch.dict(os.environ, {'PUKNOWLEDGE_CONFIG': str(cfg), 'NOVEL_WORKBENCH_CONFIG': ''}):
                settings = load_settings(neutral=True)
            self.assertEqual(settings['modules'], ['core', 'fs'])
            self.assertEqual(settings['capture'], settings['pucatch'])
            self.assertFalse(settings['capture']['enabled'])

    def test_capture_conflicts_with_pucatch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = root / 'config.json'
            cfg.write_text(json.dumps({
                'workspaces': {},
                'capture': {'enabled': True, 'base_url': 'http://127.0.0.1:8787'},
                'pucatch': {'enabled': False},
            }), encoding='utf-8')
            with patch.dict(os.environ, {'PUKNOWLEDGE_CONFIG': str(cfg), 'NOVEL_WORKBENCH_CONFIG': ''}):
                with self.assertRaises(ValueError):
                    load_settings(neutral=True)

    def test_invalid_module_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = root / 'config.json'
            cfg.write_text(json.dumps({'workspaces': {}, 'modules': ['nope']}), encoding='utf-8')
            with patch.dict(os.environ, {'PUKNOWLEDGE_CONFIG': str(cfg), 'NOVEL_WORKBENCH_CONFIG': ''}):
                with self.assertRaises(ValueError):
                    load_settings(neutral=True)


if __name__ == '__main__':
    unittest.main()
