import asyncio
import json
import os
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from compatibility_probe import PROFILES, _environment, prepare_host_fixture, run_profiles


class CompatibilityProbeTests(unittest.TestCase):
    def test_probe_removes_external_config_and_data_overrides(self):
        config = ROOT / 'synthetic-config.json'
        with patch.dict(os.environ, {
                'PUKNOWLEDGE_CONFIG': '/private/old.json',
                'NOVEL_WORKBENCH_CONFIG': '/private/legacy.json',
                'NOVEL_WORKBENCH_DATA': '/private/real-data'}, clear=False):
            env = _environment(config)
        self.assertEqual(env['PUKNOWLEDGE_CONFIG'], str(config))
        self.assertNotIn('NOVEL_WORKBENCH_CONFIG', env)
        self.assertNotIn('NOVEL_WORKBENCH_DATA', env)

    def test_probe_is_packaged_as_a_console_command(self):
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        self.assertEqual(project['project']['scripts']['puknowledge-compat'], 'compatibility_probe:main')
        self.assertIn('compatibility_probe', project['tool']['setuptools']['py-modules'])

    def test_all_simulated_profiles_are_explicit_and_pass(self):
        report = asyncio.run(run_profiles(list(PROFILES)))
        self.assertEqual(report['state'], 'PASS', report)
        self.assertTrue(report['simulated'])
        self.assertFalse(report['real_host_verified'])
        self.assertEqual([item['profile'] for item in report['profiles']], list(PROFILES))
        cached = next(item for item in report['profiles'] if item['profile'] == 'cached-tools')
        self.assertEqual(cached['state'], 'PASS')

    def test_longform_profile_covers_restart_draft_and_isolation(self):
        self.assertIn('longform-basic', PROFILES)
        report = asyncio.run(run_profiles(['longform-basic']))
        self.assertEqual(report['state'], 'PASS', report)
        profile = report['profiles'][0]
        checks = {item['id']: item for item in profile['checks']}
        for name in ('longform_tool_discovery', 'writing_snapshot_non_canon',
                     'draft_preview_save', 'longform_restart_recovery',
                     'longform_project_isolation'):
            self.assertTrue(checks[name]['passed'], checks[name])

    def test_cli_emits_machine_readable_protocol_only_report(self):
        env = os.environ.copy(); env['PYTHONPATH'] = str(ROOT / 'scripts')
        result = subprocess.run([sys.executable, '-B', '-m', 'compatibility_probe', '--profile', 'tools-only'],
                                cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['state'], 'PASS')
        self.assertTrue(report['simulated']); self.assertFalse(report['real_host_verified'])

    def test_bounded_profile_detects_an_insufficient_budget(self):
        report = asyncio.run(run_profiles(['bounded-response'], response_budget=2000))
        self.assertEqual(report['state'], 'FAIL', report)
        checks = report['profiles'][0]['checks']
        budget = next(item for item in checks if item['id'] == 'response_budget')
        self.assertFalse(budget['passed'])

    def test_prepare_host_fixture_is_explicit_synthetic_and_refuses_overwrite(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'host-acceptance'
            report = prepare_host_fixture(output)
            self.assertEqual(report['state'], 'READY')
            self.assertTrue(report['synthetic'])
            self.assertFalse(report['database_created'])
            config = json.loads(Path(report['config']).read_text(encoding='utf-8'))
            self.assertEqual(config['modules'], ['core', 'fs', 'longform'])
            self.assertEqual(sorted(config['workspaces']), ['alpha', 'beta'])
            self.assertEqual(sorted(path.name for path in (output / 'longform-projects').iterdir()),
                             ['story-alpha', 'story-beta'])
            self.assertFalse((output / 'data').exists())
            with self.assertRaises(ValueError):
                prepare_host_fixture(output)

    def test_cli_prepares_machine_readable_host_fixture(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'external-host'
            env = os.environ.copy(); env['PYTHONPATH'] = str(ROOT / 'scripts')
            result = subprocess.run([sys.executable, '-B', '-m', 'compatibility_probe',
                                     '--prepare-host', str(output)], cwd=ROOT, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['state'], 'READY')
            self.assertEqual(report['mcp']['transport'], 'stdio')


if __name__ == '__main__':
    unittest.main()
