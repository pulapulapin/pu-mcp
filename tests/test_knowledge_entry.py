import asyncio,json,os,sys,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from novel_config import load_settings
class KnowledgeEntryTests(unittest.TestCase):
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
     defs=(await s.list_tools()).tools;names={x.name for x in defs};self.assertEqual(len(names),41)
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
