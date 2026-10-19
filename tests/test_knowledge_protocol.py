import asyncio,json,os,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];MODULE_ROOT=os.environ.get('PUKNOWLEDGE_MODULE_ROOT',str(ROOT/'scripts'));sys.path.insert(0,MODULE_ROOT)
class KnowledgeProtocolTests(unittest.TestCase):
 def test_stdio_public_dataset_roundtrip(self):asyncio.run(self.stdio())
 async def stdio(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);config=root/'config.json';config.write_text(json.dumps({'data_dir':str(root/'data'),'workspaces':{'sample':{'path':d,'label':'Sample','domain':'test'}}}))
   params=StdioServerParameters(command=sys.executable,args=['-B','-m','knowledge_entry','--config',str(config)],cwd=d,env={**os.environ,'PYTHONPATH':MODULE_ROOT})
   async with stdio_client(params) as (r,w):
    async with ClientSession(r,w) as s:
     await s.initialize();names={t.name for t in (await s.list_tools()).tools};self.assertIn('import_commit',names)
     async def call(name,args):
      result=json.loads((await s.call_tool(name,args)).content[0].text);self.assertTrue(result['ok'],result);return result['result']
     args={'project':'sample','dataset_id':'tools','body':{'title':'合成工具能力','scope':'project','purpose':'reference'},'baseline':0};p=await call('dataset_preview',args);await call('dataset_save',{**args,'preview_fingerprint':p['preview_fingerprint'],'operation_key':'create'});row=await call('dataset_get',{'project':'sample','dataset_id':'tools'});self.assertEqual(row['body']['title'],'合成工具能力')
     schema={'project':'sample','dataset_id':'tools','object_id':'capability','body':{'fields':{'provider':{'type':'string','required':True}},'allowed_relations':[]},'baseline':1};p=await call('schema_preview',schema);await call('schema_save',{**schema,'preview_fingerprint':p['preview_fingerprint'],'operation_key':'schema'})
     text=json.dumps([{'id':'sample-tool','body':{'record_type':'capability','schema_revision':1,'values':{'provider':'synthetic'},'evidence':[]}}]);batch={'project':'sample','dataset_id':'tools','baseline':2,'format':'json','content':text};p=await call('import_preview',batch);saved=await call('import_commit',{**batch,'preview_fingerprint':p['preview_fingerprint'],'operation_key':'batch'});self.assertEqual(saved['count'],1);q=await call('record_query',{'project':'sample','dataset_id':'tools','filters':[{'field':'provider','op':'eq','value':'synthetic'}]});self.assertEqual(q['records'][0]['object_id'],'sample-tool')

 def test_http_uses_same_service_and_rejects_browser_origin(self):
  from knowledge_http import make_server
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);config=root/'config.json';config.write_text(json.dumps({'data_dir':str(root/'data'),'workspaces':{'sample':{'path':d,'label':'Sample','domain':'test'}}}))
   with patch.dict(os.environ,{'NOVEL_WORKBENCH_CONFIG':str(config),'PUKNOWLEDGE_CONFIG':str(config),'NOVEL_WORKBENCH_DATA':str(root/'data')}):
    server=make_server(port=0);threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
     base=f'http://127.0.0.1:{server.server_port}/api/v1/knowledge/'
     def post(op,data,origin=''):
      req=Request(base+op,json.dumps(data).encode(),headers={'Content-Type':'application/json',**({'Origin':origin} if origin else {})});return json.load(urlopen(req))
     args={'project':'sample','dataset_id':'tools','body':{'title':'合成HTTP','scope':'global','purpose':'reference'},'baseline':0};p=post('dataset_preview',args)['result'];saved=post('dataset_save',{**args,'preview_fingerprint':p['preview_fingerprint'],'operation_key':'create'})['result'];self.assertEqual(saved['revision'],1)
     self.assertEqual(post('dataset_get',{'project':'sample','dataset_id':'tools'})['result']['body']['title'],'合成HTTP')
     try:post('dataset_get',{'project':'sample','dataset_id':'tools'},'https://untrusted.example')
     except HTTPError as exc:self.assertEqual(exc.code,403);exc.close()
     else:self.fail('browser request accepted')
     try:post('__getattribute__',{})
     except HTTPError as exc:self.assertEqual(exc.code,400);exc.close()
     else:self.fail('unknown operation accepted')
    finally:server.shutdown();server.server_close()
