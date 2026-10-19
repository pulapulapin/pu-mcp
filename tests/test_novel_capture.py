import hashlib,json,os,sys,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from novel_capture import Capture,public_url
from novel_config import load_settings

class CaptureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.calls=[];self.body='甲乙\n丙丁\n';self.state='completed';self.bad_sha=False;self.error=False;self.cap_failed=False;self.jobid='abcdef123456';outer=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def send(self,data,status=200):
    raw=json.dumps(data).encode();self.send_response(status);self.end_headers();self.wfile.write(raw)
   def do_GET(self):
    if self.path.endswith('/capabilities'):return self.send({'service':{'service_version':'fixture','api_version':'1'},'capabilities':[{'id':name,'levels':{'dependencies_available':True,'sample_verified':'failed' if outer.cap_failed else 'not_verified'}} for name in ('link.probe.video','link.probe.article','link.probe.audio','task.create.article','task.create.video','task.create.audio')]})
    if self.path.endswith('/artifacts'):return self.send({'artifacts':[{'artifact_id':'abcdef123456-0','type':'article_markdown','bytes':len(outer.body.encode()),'sha256':'0'*64 if outer.bad_sha else hashlib.sha256(outer.body.encode()).hexdigest(),'source_url':'https://example.org/research','state':'completed'}]})
    if '/content?' in self.path:
     from urllib.parse import parse_qs,urlsplit
     q=parse_qs(urlsplit(self.path).query);start=int(q['offset'][0]);end=min(len(outer.body),start+int(q['limit'][0]));return self.send({'content':outer.body[start:end],'next_offset':end,'eof':end==len(outer.body),'content_fingerprint':'sha256:'+hashlib.sha256(outer.body.encode()).hexdigest()})
    return self.send({'task_id':outer.jobid,'state':outer.state,'source_url':'https://example.org/research','content_type':'article'})
   def do_POST(self):
    data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or '{}');outer.calls.append((self.path,data,self.headers.get('Idempotency-Key')))
    if outer.error:return self.send({'error':{'code':'AUTH_REQUIRED','message':'private-token-cookie','retryable':False,'details':{}}},401)
    if self.path.endswith('/probe'):return self.send({'title':'公开样例','size':{'bytes':None},'supports_capture':True,'auth':'public'})
    if self.path.endswith('/cancel'):return self.send({'cancel_requested':True})
    return self.send({'task_id':outer.jobid,'state':'queued'},202)
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  self.file=self.root/'config.json';self.file.write_text(json.dumps({'data_dir':'data','pucatch':{'enabled':True,'base_url':f'http://127.0.0.1:{server.server_port}'}}))
  env=patch.dict(os.environ,{'NOVEL_WORKBENCH_CONFIG':str(self.file),'PUKNOWLEDGE_CONFIG':str(self.file),'NOVEL_WORKBENCH_DATA':str(self.root/'data')});env.start();self.addCleanup(env.stop);self.c=Capture();self.url='https://example.org/research'
 def start(self,**kw):return self.c.start(self.url,'article','核对来源','one',expected_bytes=1000,**kw)
 def test_http_probe_needs_no_source_checkout_and_public_auth(self):
  self.assertEqual(self.c.probe(self.url,'video')['metadata']['title'],'公开样例');self.assertEqual(self.calls[0][0],'/api/v1/probe');self.assertEqual(self.calls[0][1]['auth'],'public')
 def test_capability_report_does_not_claim_execution(self):
  c=self.c.capabilities();self.assertEqual(c['reported_version'],'fixture');self.assertFalse(c['execution_verified']);self.assertEqual(c['manifest']['capabilities'][0]['levels']['sample_verified'],'not_verified')
 def test_article_payload_idempotency_and_no_budget(self):
  self.start();self.assertTrue(self.start()['reused']);self.assertEqual(len(self.calls),1);route,payload,key=self.calls[0];self.assertEqual(route,'/api/v1/tasks');self.assertNotIn('budget_bytes',payload);self.assertEqual(payload['auth'],'public');self.assertTrue(key)
  with self.assertRaises(ValueError):self.c.start(self.url,'video','different','one',expected_bytes=1000)
 def test_media_enforced_budget_and_unknown_not_allowed(self):
  self.c.start(self.url,'video','核对','video',expected_bytes=1000);self.assertEqual(self.calls[-1][1]['budget_bytes'],1000)
  for size in (None,True,-1,1_000_000_001):
   with self.assertRaises(ValueError):self.c.start(self.url,'video','核对','blocked',expected_bytes=size)
 def test_error_code_preserved_no_sensitive_server_message(self):
  self.error=True
  with self.assertRaisesRegex(ValueError,'AUTH_REQUIRED') as caught:self.c.probe(self.url,'article')
  self.assertNotIn('private-token-cookie',str(caught.exception))
 def test_article_read_uses_api_and_checks_whole_fingerprint(self):
  self.start();a=self.c.read_article(self.jobid,max_chars=3);b=self.c.read_article(self.jobid,char_offset=a['next_char_offset'],expected_fingerprint=a['fingerprint']);self.assertEqual(a['body']+b['body'],self.body);self.assertNotIn('path',a)
  self.bad_sha=True
  with self.assertRaises(ValueError):self.c.read_article(self.jobid)
 def test_unknown_is_not_completed(self):
  self.start();self.state='unknown'
  with self.assertRaises(ValueError):self.c.read_article(self.jobid)
 def test_scoped_jobs_and_stale_task_ref(self):
  from research_workspace import ResearchWorkspace
  folder=self.root/'project';folder.mkdir();raw=json.loads(self.file.read_text());raw['workspaces']={k:{'path':str(folder),'label':k,'domain':'research'} for k in ('tools','other')};self.file.write_text(json.dumps(raw))
  w=ResearchWorkspace();snap={'task':'test','summary':'synthetic','next_step':'read','task_context':{'task_id':'collect','stage':'capture','state':'active','direction_revision':1}};p=w.conversations.preview('tools','current',snap);r=w.conversations.save('tools','current',snap,0,p['preview_fingerprint'],'task');ref={k:r[k] for k in ('session_id','revision','fingerprint')}
  self.start(project='tools',task_ref=ref);self.assertEqual(self.c.list_jobs('tools')['total'],1);self.assertEqual(self.c.list_jobs('other')['total'],0)
  with self.assertRaises(ValueError):self.c.cancel(self.jobid,'other')
  self.assertTrue(self.c.cancel(self.jobid,'tools')['cancel_requested']);ref['fingerprint']='0'*64
  with self.assertRaises(ValueError):self.c.start(self.url,'article','test','stale',project='tools',task_ref=ref,expected_bytes=1000)
 def test_cumulative_and_uncertain_are_not_retried(self):
  self.c.start(self.url,'video','核对','first',expected_bytes=600_000_000)
  with self.assertRaises(ValueError):self.c.start(self.url,'video','核对','second',expected_bytes=500_000_000)
  request=self.c.request
  def fail_submission(route,*args):
   if route=='/api/v1/tasks':raise ValueError('submission connection lost')
   return request(route,*args)
  with patch.object(self.c,'request',side_effect=fail_submission):
   with self.assertRaises(ValueError):self.c.start(self.url,'article','核对','uncertain',expected_bytes=100)
  before=len(self.calls)
  with self.assertRaises(ValueError):self.c.start(self.url,'article','核对','uncertain',expected_bytes=100)
  self.assertEqual(len(self.calls),before)
 def test_private_urls_and_backend_config_rejected(self):
  for url in ('http://127.0.0.1','http://10.0.0.1','file:///tmp/a','http://localhost','https://u:p'+'@example.org'):
   with self.assertRaises(ValueError):public_url(url)
  for url in ('https://example.org','http://localhost:8787','http://127.0.0.1:8787/path'):
   self.file.write_text(json.dumps({'pucatch':{'enabled':True,'base_url':url}}))
   with self.assertRaises(ValueError):load_settings()

 def test_failed_reported_capability_prevents_execution(self):
  self.cap_failed=True
  with self.assertRaises(ValueError):self.c.probe(self.url,'video')
  with self.assertRaises(ValueError):self.start()
  self.assertEqual(self.calls,[])
