import ast,asyncio,json,os,sys,tempfile,unittest,subprocess,tomllib
from pathlib import Path
from unittest.mock import patch
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from novel_config import load_settings
class KnowledgeEntryTests(unittest.TestCase):
 def test_release_versions_are_aligned(self):
  from novel_version import VERSION
  project=tomllib.loads((ROOT/'pyproject.toml').read_text())
  plugin=json.loads((ROOT/'plugins/pu-knowledge-workbench/plugin.json').read_text())
  self.assertEqual(VERSION,'0.4.0')
  self.assertEqual(project['project']['version'],VERSION)
  self.assertEqual(plugin['version'],VERSION)

 def test_onboarding_module_is_packaged(self):
  project=tomllib.loads((ROOT/'pyproject.toml').read_text())
  self.assertIn('onboarding',project['tool']['setuptools']['py-modules'])

 def test_packaged_modules_have_no_undeclared_local_imports(self):
  project=tomllib.loads((ROOT/'pyproject.toml').read_text())
  modules=set(project['tool']['setuptools']['py-modules']);imports=set()
  for name in modules:
   tree=ast.parse((ROOT/'scripts'/(name+'.py')).read_text())
   for node in ast.walk(tree):
    if isinstance(node,ast.Import):imports.update(alias.name.split('.')[0] for alias in node.names)
    elif isinstance(node,ast.ImportFrom) and node.module:imports.add(node.module.split('.')[0])
  allowed=set(sys.stdlib_module_names)|{'mcp','pydantic'}
  self.assertEqual(imports-modules-allowed,set())

 def run_entry(self,*args):
  return subprocess.run([sys.executable,'-B',str(ROOT/'scripts/knowledge_entry.py'),*map(str,args)],capture_output=True,text=True)

 def test_init_workspace_then_read_only_doctor(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);workspace=root/'my-project';workspace.mkdir();(workspace/'notes.md').write_text('synthetic')
   config=root/'settings'/'workspace.json'
   created=self.run_entry('--config',config,'--init-workspace',workspace,'--project-id','my-project','--label','My Project','--domain','research','--enable-fs')
   self.assertEqual(created.returncode,0,created.stderr)
   result=json.loads(created.stdout);self.assertEqual(result['state'],'CREATED');self.assertEqual(result['workspace_interface'],'task')
   self.assertEqual(config.stat().st_mode & 0o777,0o600)
   raw=json.loads(config.read_text());self.assertEqual(raw['modules'],['core','fs'])
   self.assertEqual(raw['workspaces']['my-project']['path'],str(workspace.resolve()))
   self.assertTrue(raw['workspaces']['my-project']['fs_read']['readonly'])
   self.assertFalse((config.parent/'data').exists())
   checked=self.run_entry('--config',config,'--doctor')
   self.assertEqual(checked.returncode,0,checked.stderr)
   report=json.loads(checked.stdout);self.assertTrue(report['ready']);self.assertEqual(report['state'],'READY')
   self.assertEqual({x['id'] for x in report['checks']},{'config','data_dir','projects','workspace:my-project','database'})
   self.assertFalse((config.parent/'data').exists(),'doctor must remain read-only')
   asyncio.run(self.verify_onboarded_host(config))
   duplicate=self.run_entry('--config',config,'--init-workspace',workspace,'--project-id','my-project','--label','My Project')
   self.assertNotEqual(duplicate.returncode,0);self.assertIn('已存在',duplicate.stderr)
   rejected=self.run_entry('--config',root/'other.json','--init-workspace',root/'absent','--project-id','other','--label','Other')
   self.assertNotEqual(rejected.returncode,0);self.assertFalse((root/'other.json').exists())

 async def verify_onboarded_host(self,config):
  params=StdioServerParameters(command=sys.executable,args=['-B',str(ROOT/'scripts/knowledge_entry.py'),'--config',str(config)],env=os.environ.copy())
  async with stdio_client(params) as (reader,writer):
   async with ClientSession(reader,writer) as session:
    await session.initialize();names={x.name for x in (await session.list_tools()).tools}
    self.assertIn('workspace_guide',names);self.assertIn('fs_workspace_status',names)
    listed=json.loads((await session.call_tool('workspace_list_projects',{})).content[0].text)
    self.assertTrue(listed['ok'],listed);self.assertEqual(listed['result']['projects'][0]['id'],'my-project')

 def test_doctor_blocks_missing_workspace_without_creating_it(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);missing=root/'missing';config=root/'config.json'
   config.write_text(json.dumps({'data_dir':str(root/'data'),'workspaces':{'missing':{'path':str(missing),'label':'Missing','domain':'research'}}}))
   checked=self.run_entry('--config',config,'--doctor')
   self.assertEqual(checked.returncode,3,checked.stderr)
   report=json.loads(checked.stdout);self.assertFalse(report['ready']);self.assertEqual(report['state'],'BLOCKED')
   item=next(x for x in report['checks'] if x['id']=='workspace:missing')
   self.assertEqual(item['status'],'failed');self.assertTrue(item['blocking'])
   self.assertFalse(missing.exists());self.assertFalse((root/'data').exists())

 def test_doctor_blocks_corrupt_existing_database(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);data=root/'data';data.mkdir();(data/'workspace.sqlite3').write_text('not sqlite')
   config=root/'config.json';config.write_text(json.dumps({'data_dir':str(data),'workspaces':{'sample':{'path':str(root),'label':'Sample','domain':'research'}}}))
   checked=self.run_entry('--config',config,'--doctor')
   self.assertEqual(checked.returncode,3,checked.stderr)
   report=json.loads(checked.stdout);database=next(x for x in report['checks'] if x['id']=='database')
   self.assertEqual(database['status'],'failed');self.assertTrue(database['blocking'])

 def test_neutral_config_aliases_and_conflicts(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'config.json';data={'workspaces':{'sample':{'path':str(root),'label':'Sample','domain':'research'}}};p.write_text(json.dumps(data))
   with patch.dict(os.environ,{'PUKNOWLEDGE_CONFIG':str(p),'NOVEL_WORKBENCH_CONFIG':''}):self.assertIn('sample',load_settings()['research_projects'])
   data['research_projects']={'other':{'path':str(root),'label':'other','domain':'research'}};p.write_text(json.dumps(data))
   with patch.dict(os.environ,{'PUKNOWLEDGE_CONFIG':str(p),'NOVEL_WORKBENCH_CONFIG':''}),self.assertRaises(ValueError):load_settings()
 def test_public_config_check_does_not_infer_domain_collections(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.json';p.write_text(json.dumps({'workspaces':{}}))
   result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/knowledge_entry.py'),'--config',str(p),'--check-config'],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   data=json.loads(result.stdout);self.assertIn('workspaces',data);self.assertNotIn('dnd',result.stdout.lower())
 def test_public_default_has_neutral_schema_and_requires_project(self):asyncio.run(self.protocol())
 async def protocol(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'config.json';p.write_text(json.dumps({'data_dir':str(root/'data'),'workspaces':{'sample':{'path':str(root),'label':'Sample','domain':'research'}}}))
   params=StdioServerParameters(command=sys.executable,args=['-B',str(ROOT/'scripts/knowledge_entry.py'),'--config',str(p)],cwd=str(root),env=os.environ.copy())
   async with stdio_client(params) as (r,w):
    async with ClientSession(r,w) as s:
     info=await s.initialize();self.assertEqual(info.server_info.name,'pu-knowledge-workbench')
     defs=(await s.list_tools()).tools;names={x.name for x in defs};self.assertEqual(len(names),45)
     self.assertIn('workspace_guide',names);self.assertIn('task_resume',names);self.assertIn('source_get',names);self.assertIn('tool_list_capabilities',names)
     for t in defs:self.assertNotIn('dnd',json.dumps(t.model_dump(),ensure_ascii=False).lower())
     self.assertFalse(any(n.startswith(('novel_','research_','game_')) for n in names))
     result=json.loads((await s.call_tool('task_resume',{'project':'sample'})).content[0].text)
     self.assertTrue(result['ok'],result);self.assertEqual(result['result']['resume_mode'],'unassigned')
     status=json.loads((await s.call_tool('workspace_get_status',{})).content[0].text)
     self.assertEqual(status['result']['profile'],'workspace')
     async def call(name,args):
      value=json.loads((await s.call_tool(name,args)).content[0].text)
      self.assertTrue(value['ok'],value);return value['result']
     snapshot={'task':'合成研究任务','summary':'仅验证公共接口','next_step':'核对来源','task_context':{'task_id':'review','stage':'证据核对','state':'active','direction_revision':1}}
     preview=await call('task_preview_snapshot',{'project':'sample','session_id':'current','snapshot':snapshot})
     saved=await call('task_save_snapshot',{'project':'sample','session_id':'current','snapshot':snapshot,'baseline':0,'preview_fingerprint':preview['preview_fingerprint'],'operation_key':'task'})
     resumed=await call('task_resume',{'project':'sample'})
     self.assertEqual(resumed['task_id'],'review');self.assertEqual(resumed['stage'],'证据核对')
     page=await call('task_read_snapshot',{'project':'sample','session_id':'current','revision':1,'expected_fingerprint':saved['fingerprint']})
     self.assertEqual(json.loads(page['text'])['task'],snapshot['task'])
     source={'research_source_id':'reference','title':'合成URL出处','media_type':'article','binding':{'kind':'url','locator':'https://example.invalid/reference'},'scope':'project','owner_project':'sample'}
     await call('source_register',{'source':source,'preview_only':False,'operation_key':'source'})
     reference=await call('source_get',{'project':'sample','research_source_id':'reference'})
     self.assertEqual(reference['source']['verification'],'declared_unverified')
     self.assertTrue((await s.call_tool('task_resume',{})).is_error)
     self.assertFalse((root/'story-contract.json').exists())
if __name__=='__main__':unittest.main()
