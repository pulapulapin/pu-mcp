"""Neutral core can read original story evidence without legacy aliases."""
import asyncio,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from tests.support import create_story
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
class CoreStoryEvidenceTests(unittest.TestCase):
 def test_core_reads_existing_registered_story_source(self):asyncio.run(self.protocol())
 async def protocol(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);create_story(root/'projects/story','story');config=root/'config.json';config.write_text(json.dumps({'projects_dir':str(root/'projects'),'data_dir':str(root/'data'),'workspaces':{}}));env={**os.environ,'NOVEL_WORKBENCH_CONFIG':str(config),'PUKNOWLEDGE_CONFIG':str(config),'NOVEL_WORKBENCH_DATA':str(root/'data')}
   with patch.dict(os.environ,env):
    from novel_workbench import Workbench
    w=Workbench();w.evidence.register({'research_source_id':'existing','title':'已有来源','scope':'project','owner_project':'story','media_type':'article','binding':{'kind':'url','locator':'https://example.invalid/source'}},0,'seed',False)
    expected=w.evidence.get('existing','story')['version_fingerprint']
   params=StdioServerParameters(command=sys.executable,args=['-B',str(ROOT/'scripts/knowledge_entry.py'),'--config',str(config),'--modules','core,fs,longform'],env=env,cwd=d)
   async with stdio_client(params) as (r,w):
    async with ClientSession(r,w) as s:
     await s.initialize();response=await s.call_tool('source_get',{'project':'story','research_source_id':'existing'});data=json.loads(response.content[0].text);self.assertTrue(data['ok'],data);self.assertEqual(data['result']['version_fingerprint'],expected)
     denied=json.loads((await s.call_tool('task_resume',{'project':'story'})).content[0].text);self.assertFalse(denied['ok'],'Evidence access must not enable research task inference for story projects')
