"""Real MCP calls: switching modes reads pinned data and never persists activation."""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.test_prompt_library import PromptFixture, ROOT


class PromptProtocolTests(PromptFixture):
    def test_stdio_switches_four_modes_with_version_receipts_and_no_read_side_effects(self):
        asyncio.run(self.protocol())

    async def protocol(self):
        modes = {'creative-explorer': '创意破局', 'story-director': '故事导演',
                 'novel-writer': '小说创作', 'reader-reviewer': '普通读者'}
        refs = {'novel-writer': self.base}
        for mode, name in modes.items():
            if mode != 'novel-writer':
                refs[mode] = self.save('owner', 'record', 'library', mode,
                                      self.template(prompt_id=mode, name=name))
        env = {**os.environ, 'PYTHONPATH': str(ROOT / 'scripts')}
        params = StdioServerParameters(command=sys.executable,
            args=['-B', '-m', 'knowledge_entry', '--config', str(self.config)], cwd=str(self.root), env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                definitions = {t.name: t for t in (await session.list_tools()).tools}
                self.assertIn('prompt_resolve', set(definitions))
                self.assertTrue(definitions['prompt_resolve'].annotations.read_only_hint)

                async def call(name, args, success=True):
                    result = await session.call_tool(name, args)
                    self.assertFalse(result.is_error, result)
                    payload = json.loads(result.content[0].text)
                    self.assertEqual(payload['ok'], success, payload)
                    return payload.get('result', payload)

                async def save(project, mode, body):
                    dataset = project + '-prompts'
                    current = await call('dataset_get', {'project': project, 'dataset_id': dataset})
                    args = {'project': project, 'dataset_id': dataset, 'object_id': mode,
                            'body': body, 'baseline': current['current_dataset_revision']}
                    p = await call('record_preview', args)
                    commit = {**args, 'preview_fingerprint': p['preview_fingerprint'],
                              'operation_key': project + '-' + mode}
                    saved = await call('record_save', commit)
                    self.assertEqual(await call('record_save', commit), saved)
                    await call('record_save', {**commit, 'operation_key': 'stale-' + mode}, success=False)

                for mode in modes:
                    body = self.customization(prompt_id=mode, base_record_id=mode,
                        base_revision=refs[mode]['revision'], base_fingerprint=refs[mode]['fingerprint'])
                    await save('a', mode, body)
                await save('b', 'novel-writer', self.customization(instructions_add=''))
                before = (self.root / 'data/workspace.sqlite3').read_bytes()
                listed = await call('record_query', {'project': 'a', 'dataset_id': 'library',
                    'record_type': 'prompt_template', 'filters': [{'field': 'lifecycle', 'op': 'eq', 'value': 'active'}]})
                self.assertEqual({r['object_id'] for r in listed['records']}, set(modes))
                for mode, name in modes.items():
                    result = await call('prompt_resolve', {'project': 'a', 'prompt_id': mode,
                        'customization_dataset_id': 'a-prompts', 'turn_instruction': '只讨论，不写正文。'})
                    self.assertEqual(result['effective_config']['name'], name)
                    self.assertEqual(result['base_ref']['fingerprint'], refs[mode]['fingerprint'])
                    self.assertEqual(result['effective_config']['output_preferences'], '正文')
                    self.assertEqual(result['customization_ref']['revision'], 1)
                    self.assertFalse(result['application_contract']['grants_tool_authorization'])
                other = await call('prompt_resolve', {'project': 'b', 'prompt_id': 'novel-writer',
                    'customization_dataset_id': 'b-prompts'})
                self.assertEqual(other['effective_config']['instructions'], '人物行为自然。')
                await call('prompt_resolve', {'project': 'b', 'prompt_id': 'novel-writer',
                    'customization_dataset_id': 'a-prompts'}, success=False)
                for override in (None, ''):
                    proposed = self.customization()['values']
                    if override is not None:
                        proposed['output_preferences_override'] = override
                    preview = await call('prompt_resolve', {'project': 'a', 'prompt_id': 'novel-writer',
                        'proposed_customization': proposed})
                    self.assertEqual(preview['effective_config']['output_preferences'], '正文' if override is None else '')
                guide = await call('workspace_guide', {})
                self.assertIn('prompt_resolve', guide['modules_detail']['core']['groups']['prompts'])
                self.assertEqual(before, (self.root / 'data/workspace.sqlite3').read_bytes())
                self.assertEqual((self.root / 'a/manuscript.txt').read_text(), 'Synthetic manuscript unchanged.')
