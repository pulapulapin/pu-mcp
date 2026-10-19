import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'plugins/pu-knowledge-workbench/launch.py'

class DesktopPluginTests(unittest.TestCase):
    def run_launcher(self, home, *args):
        env = os.environ.copy()
        env['HOME'] = str(home)
        env['PYTHONPATH'] = str(ROOT / 'scripts')
        return subprocess.run([sys.executable, '-B', str(LAUNCHER), *args],
                              cwd=home, env=env, capture_output=True, text=True, timeout=20)

    def test_missing_setup_fails_without_creating_data(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            result = self.run_launcher(home)
            self.assertEqual(result.returncode, 2)
            self.assertIn('--configure', result.stderr)
            self.assertEqual(list(home.iterdir()), [])

    def test_setup_validates_and_requires_explicit_replace(self):
        with tempfile.TemporaryDirectory(prefix='pu plugin ') as d:
            home = Path(d)
            config = home / 'settings with spaces.json'
            config.write_text(json.dumps({'data_dir': str(home / 'data'), 'workspaces': {}}))
            args = ('--configure', '--python', sys.executable, '--config', str(config))
            result = self.run_launcher(home, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            settings = home / '.config/puknowledge/desktop.json'
            payload = json.loads(settings.read_text())
            self.assertEqual(payload['config'], str(config.resolve()))
            self.assertEqual(payload['modules'], 'core')
            self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
            self.assertFalse((home / 'data').exists())
            self.assertEqual(self.run_launcher(home, *args).returncode, 2)
            self.assertEqual(self.run_launcher(home, *args, '--replace').returncode, 0)
            bad = self.run_launcher(home, *args, '--replace', '--modules', 'unknown')
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(json.loads(settings.read_text()), payload)

    def test_invalid_runtime_never_writes_setup(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            config = home / 'config.json'
            config.write_text('{}')
            result = self.run_launcher(home, '--configure', '--python', '/missing/python',
                                       '--config', str(config))
            self.assertEqual(result.returncode, 2)
            self.assertFalse((home / '.config').exists())

    def test_corrupt_binding_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            settings = home / '.config/puknowledge/desktop.json'
            settings.parent.mkdir(parents=True)
            settings.write_text('[]')
            result = self.run_launcher(home)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('Traceback', result.stderr)
