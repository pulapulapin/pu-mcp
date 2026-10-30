"""Module registry: core / fs / longform compose one stdio server."""
import asyncio, json, os, sys, tempfile, unittest
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
CORE = {
    'workspace_guide', 'workspace_get_status', 'workspace_list_projects', 'task_resume', 'task_preview_snapshot',
    'task_save_snapshot', 'task_list_snapshots', 'task_read_snapshot', 'tool_list_capabilities',
    'source_register', 'source_get', 'source_link_project', 'evidence_preview', 'evidence_save',
    'evidence_query', 'capture_get_status', 'capture_probe_url', 'capture_start', 'capture_get_job',
    'capture_list_jobs', 'capture_cancel_job', 'capture_read_article', 'dataset_preview', 'dataset_save',
    'dataset_get', 'schema_preview', 'schema_save', 'schema_get', 'record_preview', 'record_save',
    'record_get', 'record_query', 'relation_preview', 'relation_save', 'relation_query',
    'dataset_validate', 'import_preview', 'import_commit',
    'prompt_resolve',
    'project_storage_get', 'project_storage_preview',
}
FS = {'fs_workspace_status', 'fs_list_files', 'fs_read_file', 'fs_search'}
LONGFORM_PUBLIC = {
    'writing_get_state', 'writing_get_context', 'writing_resume', 'writing_validate',
    'writing_save_confirmed_decision', 'draft_list', 'draft_get', 'draft_propose',
    'draft_propose_edit', 'draft_preview', 'draft_save', 'draft_reject', 'draft_export',
    'library_list_books', 'library_index_book', 'library_get_structure', 'library_read_excerpt',
    'library_search', 'library_register_book', 'library_set_active', 'library_inspect_file',
    'library_get_progress', 'library_record_progress',
    'story_plan_bootstrap', 'story_plan_get', 'story_plan_preview', 'story_plan_save',
    'story_chapter_context', 'story_consistency_review',
}


def _config(root: Path, fs=False):
    workspaces = {'sample': {'path': str(root), 'label': 'Sample', 'domain': 'research'}}
    if fs:
        workspaces['sample']['fs_read'] = {'enabled': True, 'readonly': True}
        (root / 'note.md').write_text('# hello\nfs-ok\n', encoding='utf-8')
    cfg = root / 'config.json'
    cfg.write_text(json.dumps({'data_dir': str(root / 'data'), 'workspaces': workspaces}), encoding='utf-8')
    return cfg


async def _tools(args, cfg, root):
    env = {**os.environ, 'PUKNOWLEDGE_CONFIG': str(cfg), 'NOVEL_WORKBENCH_CONFIG': str(cfg)}
    params = StdioServerParameters(command=PYTHON, args=args, cwd=str(root), env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return {t.name for t in (await s.list_tools()).tools}


class ModuleServerTests(unittest.TestCase):
    def test_core_only_is_workspace_surface(self):
        asyncio.run(self._core())

    async def _core(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = _config(root)
            names = await _tools(['-B', str(ROOT / 'scripts/knowledge_entry.py'), '--config', str(cfg)], cfg, root)
            self.assertEqual(names, CORE)
            self.assertEqual(len(names), 41)

    def test_modules_core_fs_adds_four_fs_tools(self):
        asyncio.run(self._core_fs())

    async def _core_fs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = _config(root, fs=True)
            names = await _tools(
                ['-B', str(ROOT / 'scripts/knowledge_entry.py'), '--config', str(cfg), '--modules', 'core,fs'],
                cfg, root)
            self.assertEqual(names, CORE | FS)
            self.assertEqual(len(names), 45)
            env = {**os.environ, 'PUKNOWLEDGE_CONFIG': str(cfg), 'NOVEL_WORKBENCH_CONFIG': str(cfg)}
            params = StdioServerParameters(
                command=PYTHON,
                args=['-B', str(ROOT / 'scripts/knowledge_entry.py'), '--config', str(cfg), '--modules', 'core,fs'],
                cwd=str(root), env=env)
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    status = json.loads((await s.call_tool('fs_workspace_status', {})).content[0].text)
                    self.assertTrue(status['ok'], status)
                    self.assertEqual(status['result']['workspaces'][0]['project'], 'sample')
                    listed = json.loads((await s.call_tool('fs_list_files', {'project': 'sample'})).content[0].text)
                    self.assertTrue(listed['ok'], listed)
                    paths = {x['path'] for x in listed['result']['files']}
                    self.assertIn('note.md', paths)

    def test_longform_exposes_neutral_names_without_dnd_default(self):
        asyncio.run(self._longform())

    async def _longform(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = _config(root)
            names = await _tools(
                ['-B', str(ROOT / 'scripts/knowledge_entry.py'), '--config', str(cfg),
                 '--modules', 'core,longform'],
                cfg, root)
            self.assertTrue(LONGFORM_PUBLIC <= names)
            self.assertFalse(any(n.startswith('novel_') for n in names))
            schema = None
            env = {**os.environ, 'PUKNOWLEDGE_CONFIG': str(cfg), 'NOVEL_WORKBENCH_CONFIG': str(cfg)}
            params = StdioServerParameters(
                command=PYTHON,
                args=['-B', str(ROOT / 'scripts/knowledge_entry.py'), '--config', str(cfg),
                      '--modules', 'core,longform'],
                cwd=str(root), env=env)
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    for t in (await s.list_tools()).tools:
                        blob = json.dumps(t.model_dump(), ensure_ascii=False).lower()
                        self.assertNotIn("'dnd'", blob)
                        self.assertNotIn('"dnd"', blob)
                        if t.name == 'draft_list':
                            schema = t.input_schema
                    self.assertIsNotNone(schema)
                    props = schema.get('properties') or {}
                    self.assertIn('project', props)
                    self.assertNotEqual((props.get('project') or {}).get('default'), 'dnd')

    def test_unknown_module_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = _config(root)
            result = __import__('subprocess').run(
                [PYTHON, '-B', str(ROOT / 'scripts/knowledge_entry.py'), '--config', str(cfg),
                 '--modules', 'core,nope', '--check-config'],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('模块', result.stderr)

    def test_workspace_guide_lists_loaded_modules_and_quick_start(self):
        asyncio.run(self._guide())

    async def _guide(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = _config(root, fs=True)
            env = {**os.environ, 'PUKNOWLEDGE_CONFIG': str(cfg), 'NOVEL_WORKBENCH_CONFIG': str(cfg)}
            params = StdioServerParameters(
                command=PYTHON,
                args=['-B', str(ROOT / 'scripts/knowledge_entry.py'), '--config', str(cfg),
                      '--modules', 'core,fs,longform'],
                cwd=str(root), env=env)
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    names = {t.name for t in (await s.list_tools()).tools}
                    self.assertIn('workspace_guide', names)
                    self.assertFalse(any(n.startswith('novel_') for n in names))
                    guide = json.loads((await s.call_tool('workspace_guide', {})).content[0].text)
                    self.assertTrue(guide['ok'], guide)
                    self.assertEqual(guide['result']['modules'], ['core', 'fs', 'longform'])
                    architecture = guide['result']['architecture']
                    self.assertEqual(architecture['model'], 'base_plus_extensions')
                    self.assertEqual(architecture['base']['module_id'], 'core')
                    self.assertEqual(
                        [item['module_id'] for item in architecture['extensions']],
                        ['fs', 'longform'],
                    )
                    self.assertEqual(guide['result']['quick_start'][0]['tool'], 'workspace_guide')
                    tools = [x['tool'] for x in guide['result']['quick_start']]
                    self.assertIn('writing_resume', tools)
                    self.assertIn('fs_workspace_status', tools)


if __name__ == '__main__':
    unittest.main()

class NeutralDailyContractTests(unittest.TestCase):
    def test_daily_profile_has_writing_snapshots_and_real_brainstorming_guide(self):
        asyncio.run(self.protocol())

    async def protocol(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=_config(root,fs=True)
            from tests.support import create_story
            create_story(root/'projects/story','story')
            data=json.loads(cfg.read_text());data['projects_dir']=str(root/'projects');data['modules']=['core','fs','longform'];cfg.write_text(json.dumps(data))
            params=StdioServerParameters(command=PYTHON,args=['-B',str(ROOT/'scripts/knowledge_entry.py'),'--config',str(cfg)],cwd=d,env={**os.environ,'PUKNOWLEDGE_CONFIG':str(cfg),'NOVEL_WORKBENCH_CONFIG':str(cfg)})
            async with stdio_client(params) as (r,w):
                async with ClientSession(r,w) as s:
                    await s.initialize();names={t.name for t in (await s.list_tools()).tools}
                    required={'writing_preview_snapshot','writing_save_snapshot','writing_list_snapshots','writing_read_snapshot','writing_resume','workspace_guide'}|FS
                    self.assertTrue(required<=names,required-names);self.assertFalse(any(n.startswith(('novel_','research_','voice_','game_')) for n in names))
                    async def call(name,args):
                        value=json.loads((await s.call_tool(name,args)).content[0].text);self.assertTrue(value.get('ok'),value);return value.get('result',value)
                    guide=await call('workspace_guide',{});self.assertEqual(guide['modules'],['core','fs','longform'])
                    for info in guide['modules_detail'].values():self.assertTrue(set(info.get('first',[]))<=names)
                    self.assertIn('snapshot_contract',guide)
                    projects={x['id']:x for x in (await call('workspace_list_projects',{}))['projects']}
                    self.assertEqual(projects['story']['workspace_interface'],'writing')
                    self.assertEqual(projects['sample']['workspace_interface'],'task')
                    self.assertIn('note.md',{x['path'] for x in (await call('fs_list_files',{'project':'sample'}))['files']})
                    snapshot={'task':'synthetic writing task','summary':'test only','next_step':'read','task_context':{'task_id':'writing','stage':'draft','state':'active','direction_revision':1}}
                    args={'project':'story','session_id':'current','snapshot':snapshot};p=await call('writing_preview_snapshot',args);saved=await call('writing_save_snapshot',{**args,'baseline':0,'preview_fingerprint':p['preview_fingerprint'],'operation_key':'write'})
                    self.assertEqual((await call('writing_list_snapshots',{'project':'story'}))['total'],1)
                    text=await call('writing_read_snapshot',{'project':'story','session_id':'current','revision':1,'expected_fingerprint':saved['fingerprint']});self.assertEqual(json.loads(text['text'])['task'],snapshot['task'])
                    self.assertEqual((await call('writing_resume',{'project':'story'}))['task_id'],'writing')
