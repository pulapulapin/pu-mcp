"""Neutral corpus extension: preview, rebuild, search and exact-version read."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class CorpusExtensionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.refs = self.root / 'refs'
        self.refs.mkdir()
        (self.refs / 'sample.md').write_text('通用产品资料\n能力 证据 版本\n', encoding='utf-8')
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({
            'data_dir': str(self.root / 'data'),
            'workspaces': {},
            'collections': {'sample': str(self.refs)},
        }), encoding='utf-8')

    def test_importing_corpus_does_not_load_dnd_domain_pack(self):
        code = (
            "import sys;sys.path.insert(0," + repr(str(ROOT / 'scripts')) + ");"
            "import corpus;assert 'domain_dnd' not in sys.modules;"
            "assert 'domain_dnd_cards' not in sys.modules"
        )
        result = subprocess.run([PYTHON, '-B', '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mcp_corpus_is_neutral_and_version_exact(self):
        asyncio.run(self._protocol())

    async def _protocol(self):
        env = {
            **os.environ,
            'PUKNOWLEDGE_CONFIG': str(self.config),
            'NOVEL_WORKBENCH_CONFIG': str(self.config),
        }
        params = StdioServerParameters(
            command=PYTHON,
            args=['-B', str(ROOT / 'scripts/knowledge_entry.py'), '--config', str(self.config),
                  '--modules', 'core,corpus'],
            cwd=str(self.root),
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                definitions = (await session.list_tools()).tools
                names = {tool.name for tool in definitions}
                corpus_names = {
                    'corpus_list_collections', 'corpus_preview_index', 'corpus_commit_index',
                    'corpus_search', 'corpus_read_document',
                }
                self.assertTrue(corpus_names <= names)
                self.assertFalse(any(name.startswith('novel_') for name in names))
                for tool in definitions:
                    if tool.name.startswith('corpus_'):
                        self.assertNotIn('dnd', json.dumps(tool.model_dump(), ensure_ascii=False).lower())

                async def call(name, arguments):
                    payload = json.loads((await session.call_tool(name, arguments)).content[0].text)
                    self.assertTrue(payload['ok'], payload)
                    return payload['result']

                preview = await call('corpus_preview_index', {'collection': 'sample'})
                self.assertEqual(preview['changes'][0]['action'], 'add')
                saved = await call('corpus_commit_index', {
                    'collection': 'sample',
                    'preview_fingerprint': preview['preview_fingerprint'],
                })
                self.assertTrue(saved['saved'])
                hit = (await call('corpus_search', {
                    'query': '能力 证据', 'collection': 'sample', 'match_mode': 'all',
                }))['hits'][0]
                self.assertEqual(hit['document_ref']['kind'], 'corpus_document')
                self.assertEqual(
                    set(hit['document_ref']),
                    {'kind', 'source_id', 'fingerprint'},
                )
                self.assertNotIn('edition', hit)
                page = await call('corpus_read_document', {
                    'source_id': hit['source_id'],
                    'expected_fingerprint': hit['fingerprint'],
                })
                self.assertIn('能力 证据 版本', page['text'])
                self.assertTrue(page['current'])

                (self.refs / 'sample.md').write_text('已经变化\n', encoding='utf-8')
                stale = json.loads((await session.call_tool('corpus_commit_index', {
                    'collection': 'sample',
                    'preview_fingerprint': preview['preview_fingerprint'],
                })).content[0].text)
                self.assertFalse(stale['ok'])
                historical = await call('corpus_read_document', {
                    'source_id': hit['source_id'],
                    'expected_fingerprint': hit['fingerprint'],
                })
                self.assertIn('能力 证据 版本', historical['text'])
                self.assertFalse(historical['current'])
                self.assertEqual(historical['source_state'], 'source_file_changed')


if __name__ == '__main__':
    unittest.main()
