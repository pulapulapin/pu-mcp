"""Real MCP protocol with synthetic media and isolated projects; not host acceptance."""
import asyncio
import sys
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
NEW = {'source_register', 'source_get', 'source_link_project', 'evidence_preview', 'evidence_save', 'evidence_query'}

class EvidenceMCPTests(unittest.TestCase):
    def test_real_stdio_cross_project_and_restart(self):
        asyncio.run(self.verify())
    async def verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            for project in ('a','b'):(root/'projects'/project).mkdir(parents=True)
            video=root/'sample.mp4';video.write_bytes(b'synthetic fixture, not real video')
            config=root/'config.json'
            config.write_text(json.dumps({
                'data_dir':str(root/'db'),'projects_dir':str(root/'projects'),'research_roots':[str(root)],
                'workspaces':{p:{'path':str(root/'projects'/p),'label':p,'domain':'research'} for p in ('a','b')},
            }))
            params=StdioServerParameters(command=sys.executable,args=['-B',str(ROOT/'scripts/knowledge_entry.py'),'--config',str(config)],cwd=str(root),env={**os.environ,'PUKNOWLEDGE_CONFIG':str(config)})
            for restarted in (False,True):
                async with stdio_client(params) as (read,write):
                    async with ClientSession(read,write) as session:
                        info=await session.initialize()
                        self.assertEqual(info.server_info.version,'0.3.3')
                        definitions=(await session.list_tools()).tools
                        self.assertIn('workspace_guide',{t.name for t in definitions})
                        self.assertTrue(NEW <= {t.name for t in definitions})
                        self.assertIn('workspace_guide',{t.name for t in definitions})
                        for definition in definitions:
                            if definition.name in NEW-{'source_register'}:
                                self.assertTrue('project' in definition.input_schema.get('required',[]) or definition.name in ('evidence_preview','evidence_save'))
                        async def call(name,args):
                            result=await session.call_tool(name,args)
                            self.assertFalse(result.is_error,(name,result))
                            payload=json.loads(result.content[0].text)
                            self.assertTrue(payload['ok'],payload)
                            return payload['result']
                        if restarted:
                            for project in ('a','b'):
                                self.assertEqual((await call('evidence_query',{'project':project}))['total'],1)
                            continue
                        source={'research_source_id':'mcp-video','title':'媒体验收样本','media_type':'video','binding':{'kind':'local_file','locator':str(video)}}
                        preview=await call('source_register',{'source':source})
                        self.assertFalse(preview['saved'])
                        source['expected_fingerprint']=preview['fingerprint']
                        args={'source':source,'preview_only':False,'operation_key':'register'}
                        registered=await call('source_register',args)
                        self.assertEqual(registered,await call('source_register',args))
                        for project in ('a','b'):
                            await call('source_link_project',{'research_source_id':'mcp-video','project':project,'purpose':'独立目的'+project,'baseline':0,'operation_key':'link'})
                            annotation={'annotation_id':'sample','project':project,'research_source_id':'mcp-video','source_revision':1,'position':{'type':'time_range','start_ms':1000,'end_ms':2000},'content_type':'owner_note','content':'测试观察'+project,'coverage':'sample','limitations':'合成样本，未观看实际视频'}
                            p=await call('evidence_preview',{'annotation':annotation})
                            save_args={'annotation':annotation,'baseline':p['baseline'],'preview_fingerprint':p['preview_fingerprint'],'operation_key':'save'}
                            first=await call('evidence_save',save_args)
                            self.assertEqual(first,await call('evidence_save',save_args))
                        self.assertEqual((await call('source_get',{'project':'a'}))['total'],1)
                        self.assertEqual(hashlib.sha256(video.read_bytes()).hexdigest(),registered['fingerprint'])

if __name__=='__main__': unittest.main()
