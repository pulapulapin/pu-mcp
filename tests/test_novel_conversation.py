import asyncio, json, os, sqlite3, sys, tempfile, unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from novel_workbench import Workbench
from novel_store import Store
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class ConversationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  projects=self.root/'projects'
  for project in ['one','two']:
   p=projects/project;p.mkdir(parents=True)
   for name in ['story-contract','world','characters','timeline','chapters']:(p/(name+'.json')).write_text('{}')
  cfg=self.root/'config.json';cfg.write_text(json.dumps({'projects_dir':str(projects),'data_dir':str(self.root/'data'),'project_states':{'two':'paused'}}))
  env=patch.dict(os.environ,{'NOVEL_WORKBENCH_CONFIG':str(cfg)});env.start();self.addCleanup(env.stop)
  self.w=Workbench()
 def data(self,**extra):return {'task':'处理长度上限','summary':'保存工作上下文','next_step':'读取交接包','decisions':['采用候选方案，需来源核对'],'candidates':['未确认设定'],'unresolved':['尚无真实登记'],'references':[{'path':'deliverables/sample.md','revision':1}],**extra}
 def save(self,data=None,baseline=0,key='save',session='chat-one',project='one'):
  data=data or self.data();p=self.w.conversations.preview(project,session,data)
  return self.w.conversations.save(project,session,data,baseline,p['preview_fingerprint'],key)
 def test_restart_restore_history_idempotency_and_old_checkpoint_preserved(self):
  self.w.save_checkpoint('one','旧任务','旧摘要','旧下一步',[],0)
  first=self.save();self.assertEqual(first,self.save())
  with self.assertRaises(ValueError):self.save(self.data(summary='冲突'),key='save')
  with self.assertRaises(ValueError):self.save(self.data(summary='过期'),key='stale')
  second=self.save(self.data(summary='第二轮'),baseline=1,key='second')
  self.assertEqual(second['revision'],2)
  restarted=Workbench();r=restarted.resume('one')
  self.assertEqual(r['resume_mode'],'session_backup');self.assertEqual(r['task'],'处理长度上限')
  self.assertEqual(r['session_backup']['summary'],'第二轮');self.assertFalse(r['session_backup']['canon'])
  self.assertEqual(r['checkpoint']['task'],'旧任务')
  old=restarted.conversations.read('one','chat-one',1,first['fingerprint'],0,6000)
  self.assertEqual(json.loads(old['text'])['summary'],'保存工作上下文')
  self.assertEqual(restarted.conversations.list('one','chat-one')['total'],2)
 def test_paging_exact_version_and_project_isolation(self):
  first=self.save(self.data(excerpts='原文'*10000));text='';offset=0
  while True:
   r=self.w.conversations.read('one','chat-one',1,first['fingerprint'],offset,6000);text+=r['text']
   if r['next_char_offset'] is None:break
   offset=r['next_char_offset']
  self.assertEqual(json.loads(text)['excerpts'],'原文'*10000)
  self.assertEqual(self.w.conversations.list('two')['total'],0)
  self.assertIsNone(self.w.resume('two')['session_backup']);self.assertFalse(self.w.resume('two')['automatic_development_allowed'])
  for args in [('two','chat-one',1,first['fingerprint'],0,6000),('one','chat-one',1,'0'*64,0,6000),('one','chat-one',1,first['fingerprint'],-1,6000)]:
   with self.assertRaises(ValueError):self.w.conversations.read(*args)
  with self.assertRaises(ValueError):self.w.conversations.preview('../one','chat-one',self.data())
 def test_preserved_excerpt_keeps_exact_whitespace(self):
  excerpt='  原文缩进。\n\n末行。\n'
  result=self.save(self.data(excerpts=excerpt))
  read=self.w.conversations.read('one','chat-one',1,result['fingerprint'],0,6000)
  self.assertEqual(json.loads(read['text'])['excerpts'],excerpt)
 def test_latest_session_selection_and_strict_bounds(self):
  self.save();self.save(self.data(task='另一任务'),session='chat-two',key='another')
  self.assertEqual(self.w.resume('one')['resume_mode'],'task_selection_required')
  self.assertIsNone(self.w.resume('one')['task'])
  self.assertEqual(self.w.resume('one',session_id='chat-one')['task'],'处理长度上限')
  for data in [self.data(excerpts='x'*30001),self.data(candidates=['x'*301]),self.data(owner_confirmed=True),self.data(summary=''),self.data(references=[{'body':'x'*5000}])]:
   with self.subTest(data_keys=list(data)),self.assertRaises(ValueError):self.w.conversations.preview('one','chat-one',data)
  with self.assertRaises(ValueError):self.w.conversations.save('one','chat-one',self.data(),False,'0'*64,'bad')
 def structured(self,task_id='task-new',direction=2,state='active',stage='场景改编'):
  return self.data(task='改编当前场景',next_step='提交场景候选',task_context={'task_id':task_id,'direction_revision':direction,'stage':stage,'state':state})
 def test_old_task_saved_later_does_not_replace_current_direction(self):
  self.save(self.structured(),session='new')
  self.save(self.structured('task-old',1,stage='资料研究'),session='old',key='old')
  r=Workbench().resume('one')
  self.assertEqual(r['session_backup']['session_id'],'new')
  self.assertEqual(r['stage'],'场景改编');self.assertEqual(r['stage_source'],'session_backup')
  self.assertEqual(r['task_id'],'task-new');self.assertEqual(r['direction_revision'],2)
  self.assertEqual(r['next_step'],'提交场景候选');self.assertTrue(r['automatic_development_allowed'])
  historical=self.w.resume('one','old')
  self.assertTrue(historical['task_selection']['historical']);self.assertFalse(historical['automatic_development_allowed'])
 def test_current_completed_or_paused_never_resurrects_older_task(self):
  self.save(self.structured('task-old',1),session='old')
  self.save(self.structured(state='completed'),session='new',key='new')
  r=self.w.resume('one');self.assertEqual(r['task_state'],'completed')
  self.assertEqual(r['task_id'],'task-new');self.assertFalse(r['automatic_development_allowed'])
  self.save(self.structured(state='paused'),baseline=1,session='new',key='paused')
  self.assertEqual(self.w.resume('one')['task_state'],'paused')
 def test_same_direction_conflict_and_immutable_session_identity(self):
  self.save(self.structured(),session='new')
  for data,session,baseline in [(self.structured('wrong',2),'other',0),(self.structured('wrong',3),'new',1),(self.data(),'new',1)]:
   with self.subTest(session=session),self.assertRaises(ValueError):self.save(data,baseline=baseline,session=session,key='invalid-'+session)
 def test_tied_sessions_and_legacy_backups_require_selection(self):
  self.save(self.structured(),session='new')
  self.save(self.structured(),session='parallel',key='parallel')
  r=self.w.resume('one');self.assertEqual(r['resume_mode'],'task_selection_required')
  self.assertIsNone(r['task']);self.assertIsNone(r['stage']);self.assertFalse(r['automatic_development_allowed'])
  self.assertEqual(r['task_selection']['candidate_total'],2)
  self.assertEqual(self.w.resume('one','new')['task_id'],'task-new')
  self.save(project='two',session='legacy-a',key='legacy-a')
  self.save(project='two',session='legacy-b',key='legacy-b')
  self.assertEqual(self.w.resume('two')['resume_mode'],'task_selection_required')
 def test_missing_explicit_session_and_unknown_legacy_stage(self):
  with self.assertRaises(ValueError):self.w.resume('one','missing')
  self.save();r=self.w.resume('one')
  self.assertIsNone(r['stage']);self.assertEqual(r['stage_source'],'unknown')
  self.assertFalse(r['automatic_development_allowed']);self.assertTrue(r['task_selection']['warnings'])
 def test_session_revision_wins_over_clock_order(self):
  self.save(self.structured(stage='研究'),session='new')
  self.save(self.structured(stage='审稿'),baseline=1,session='new',key='revision2')
  with self.w.store.connection(write=True) as db:
   db.execute("UPDATE session_backup_versions SET created='1900-01-01' WHERE session_id='new' AND revision=2")
  preview=self.w.conversations.preview('one','new',self.structured(stage='交接'))
  self.assertEqual(preview['baseline'],2)
  third=self.w.conversations.save('one','new',self.structured(stage='交接'),2,preview['preview_fingerprint'],'revision3')
  self.assertEqual(third['revision'],3);self.assertEqual(self.w.resume('one')['stage'],'交接')
 def test_conflicting_checkpoint_kept_as_historical_not_task_stage(self):
  self.w.save_checkpoint('one','旧方向','旧摘要','旧下一步',[],0)
  self.save(self.structured(),session='new')
  r=self.w.resume('one');self.assertEqual(r['stage'],'场景改编')
  self.assertEqual(r['checkpoint']['task'],'旧方向')
  self.assertTrue(any('检查点' in w for w in r['task_selection']['warnings']))
 def test_stage_progress_legacy_late_save_and_context_share_direction(self):
  self.save(self.structured(stage='研究'),session='new')
  self.save(self.structured(stage='场景审稿'),baseline=1,session='new',key='stage2')
  self.save(session='late-legacy',key='legacy')
  result=self.w.context('one')['session']
  self.assertEqual(result['stage'],'场景审稿');self.assertEqual(result['task_id'],'task-new')
  self.assertTrue(result['task_selection']['warnings'])
 def test_task_direction_conflict_rechecked_during_save(self):
  a=self.structured('task-a',1);b=self.structured('task-b',1)
  preview=self.w.conversations.preview('one','b',b)
  self.save(a,session='a')
  with self.assertRaises(ValueError):self.w.conversations.save('one','b',b,0,preview['preview_fingerprint'],'b')
  self.assertEqual(self.w.conversations.list('one')['total'],1)
 def test_legacy_snapshot_at_old_size_limit_remains_accepted(self):
  # A new optional field must not consume the legacy payload budget when absent.
  data={'task':'t'*500,'summary':'s'*2000,'next_step':'n'*1000,'decisions':['d'*300]*10,'candidates':['c'*300]*10,'unresolved':['u'*300]*7,'references':[],'excerpts':''}
  text=json.dumps({k:v for k,v in data.items() if k!='excerpts'},ensure_ascii=False,sort_keys=True,separators=(',',':'))
  data['references']=[{'note':'r'*(12000-len(text)-11)}]
  self.assertEqual(len(json.dumps({k:v for k,v in data.items() if k!='excerpts'},sort_keys=True,separators=(',',':'))),12000)
  preview=self.w.conversations.preview('one','legacy-limit',data)
  self.assertEqual(preview['summary']['task'],data['task'])
 def test_task_context_strict_validation_and_legacy_identity(self):
  from novel_conversation import encode,Snapshot
  from novel_store import digest
  data=self.data();legacy=encode(Snapshot.model_validate(data).model_dump(mode='json',exclude={'task_context'}))
  self.assertEqual(self.w.conversations.preview('one','legacy',data)['preview_fingerprint'],digest(legacy))
  for extra in [{'direction_revision':True},{'direction_revision':0},{'task_id':'bad/id'},{'stage':''},{'state':'unknown'}]:
   data=self.structured();data['task_context'].update(extra)
   with self.subTest(extra=extra),self.assertRaises(ValueError):self.w.conversations.preview('one','invalid',data)
 def test_schema6_backup_restores_to_new_directory(self):
  with self.w.store.connection(write=True) as db:
   db.execute('DROP TABLE session_backup_versions');db.execute('DROP TABLE IF EXISTS knowledge_versions');db.execute('PRAGMA user_version=6')
   db.execute("INSERT INTO checkpoints VALUES('one',5,'旧版恢复','summary','next','[]','date')")
  backup=self.w.store.backup()
  restored=Store.restore_to_new(backup['path'],self.root/'restored6')
  self.assertEqual(restored.checkpoint('one')['task'],'旧版恢复')
  with restored.connection() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)
 def test_concurrent_saves_conflict_and_preview_does_not_write(self):
  from concurrent.futures import ThreadPoolExecutor
  before=self.w.store.path.read_bytes()
  preview=self.w.conversations.preview('one','chat-one',self.data())
  self.assertEqual(before,self.w.store.path.read_bytes())
  with self.assertRaises(ValueError):self.w.conversations.save('one','chat-one',self.data(),0,'0'*64,'wrong-preview')
  def save(key):
   try:return self.w.conversations.save('one','chat-one',self.data(),0,preview['preview_fingerprint'],key)
   except ValueError:return None
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,['first','second']))
  self.assertEqual(sum(x is not None for x in results),1)
  self.assertEqual(self.w.conversations.list('one','chat-one')['total'],1)
 def test_real_protocol_new_process_resume_and_readonly_profile(self):asyncio.run(self.protocol())
 async def protocol(self):
  async def run(action):
   params=StdioServerParameters(command=str(ROOT/'.venv/bin/python'),args=['-B',str(ROOT/'scripts/knowledge_entry.py'),'--modules','core,longform'],env=os.environ.copy(),cwd=str(self.root))
   async with stdio_client(params) as (r,w):
    async with ClientSession(r,w) as client:
     await client.initialize();await action(client)
  async def call(client,name,args):
   result=await client.call_tool(name,args);self.assertFalse(result.is_error)
   data=json.loads(result.content[0].text);self.assertTrue(data['ok'],data)
   return data.get('result',data)
  saved={}
  async def write(client):
   preview=await call(client,'writing_preview_snapshot',{'project':'one','session_id':'protocol','snapshot':self.structured()})
   result=await call(client,'writing_save_snapshot',{'project':'one','session_id':'protocol','snapshot':self.structured(),'baseline':0,'preview_fingerprint':preview['preview_fingerprint'],'operation_key':'protocol'})
   saved.update(result)
  async def restore(client):
   resumed=await call(client,'writing_resume',{'project':'one','session_id':'protocol'})
   self.assertEqual(resumed['resume_mode'],'session_backup');self.assertEqual(resumed['task'],'改编当前场景')
   self.assertEqual(resumed['stage'],'场景改编')
   self.assertEqual(resumed['task_id'],'task-new')
   for name in ['writing_get_state','writing_get_context']:
    result=await call(client,name,{'project':'one'})
    self.assertEqual(result['next_task']['instruction'],'改编当前场景')
    self.assertEqual(result['next_task']['label'],'场景改编')
    self.assertEqual(result['next_task_source'],'session_backup')
    self.assertIn('project_next_task',result)
   listed=await call(client,'writing_list_snapshots',{'project':'one','session_id':'protocol'})
   self.assertEqual(listed['total'],1)
   read=await call(client,'writing_read_snapshot',{'project':'one','session_id':'protocol','revision':1,'expected_fingerprint':saved['fingerprint'],'max_chars':6000})
   self.assertEqual(json.loads(read['text'])['candidates'],['未确认设定'])
  await run(write);await run(restore)
 def test_schema6_migration_backup_rollback_and_old_tables_preserved(self):
  with self.w.store.connection(write=True) as db:
   db.execute('DROP TABLE session_backup_versions');db.execute('DROP TABLE IF EXISTS knowledge_versions');db.execute('PRAGMA user_version=6')
   db.execute("INSERT INTO checkpoints VALUES('one',4,'old','summary','next','[]','date')")
   names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
   before={n:[tuple(r) for r in db.execute('SELECT * FROM '+n)] for n in names}
  def broken(db):db.execute('CREATE TABLE broken(x)');raise RuntimeError('migration')
  with patch('novel_conversation.schema',broken),self.assertRaises(RuntimeError):Store(self.root/'data')
  with closing(sqlite3.connect(self.root/'data/workspace.sqlite3')) as db:
   self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],6)
   self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='broken'").fetchone())
  store=Store(self.root/'data')
  with store.connection() as db:
   self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)
   self.assertEqual(before,{n:[tuple(r) for r in db.execute('SELECT * FROM '+n)] for n in names})
  backups=list((self.root/'data/backups').glob('*.sqlite3'));self.assertTrue(backups)
  self.save();backup=store.backup();restored=Store.restore_to_new(backup['path'],self.root/'restored')
  with restored.connection() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM session_backup_versions').fetchone()[0],1)

if __name__=='__main__':unittest.main()
