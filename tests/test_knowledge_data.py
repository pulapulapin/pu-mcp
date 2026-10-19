import copy,hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from research_workspace import ResearchWorkspace
from novel_evidence import encode
from novel_store import digest

class KnowledgeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.config=self.root/'config.json';self.config.write_text(json.dumps({'data_dir':str(self.root/'data'),'research_roots':[str(self.root)],'workspaces':{p:{'path':str(self.root),'label':p,'domain':'test'} for p in ('owner','other')}}));env=patch.dict(os.environ,{'NOVEL_WORKBENCH_CONFIG':str(self.config),'PUKNOWLEDGE_CONFIG':str(self.config),'NOVEL_WORKBENCH_DATA':str(self.root/'data')});env.start();self.addCleanup(env.stop);self.w=ResearchWorkspace(profile='workspace')
  from knowledge_data import Knowledge
  self.k=Knowledge(self.w);self.serial=0
 def save(self,kind,oid,body,dataset='rules',project='owner',**kw):
  base=self.k.revision(dataset);args=dict(project=project,kind=kind,dataset_id=dataset,object_id=oid,body=body,baseline=base,**kw);p=self.k.preview(**args);self.serial+=1;return self.k.save(**args,preview_fingerprint=p['preview_fingerprint'],operation_key='op'+str(self.serial))
 def dataset(self,scope='global',purpose='reference'):
  return self.save('dataset','rules',{'title':'合成规则','scope':scope,'purpose':purpose})
 def schema(self):return self.save('schema','growth',{'fields':{'level':{'type':'integer','required':True,'minimum':1,'maximum':20,'unit':'level'},'formula':{'type':'string'}},'allowed_relations':['depends_on','adopts']})
 def record(self,level=1,**kw):return {'record_type':'growth','schema_revision':1,'values':{'level':level},'status':'candidate','evidence':[],**kw}
 def test_dataset_schema_record_history_snapshot_and_formula_not_executed(self):
  self.dataset();self.schema();a=self.save('record','wizard',self.record(values={'level':1,'formula':'1+2'}));b=self.save('record','wizard',self.record(2));self.assertEqual(b['revision'],2)
  old=self.k.get('other','record','rules','wizard',revision=1);self.assertEqual(old['body']['values']['level'],1);self.assertEqual(old['body']['execution'],'not_executed');self.assertEqual(self.k.query('other','rules',dataset_revision=a['dataset_revision'])['records'][0]['revision'],1)
 def test_private_scope_and_shared_write_owner(self):
  self.dataset();self.schema()
  with self.assertRaises(ValueError):self.save('record','bad',self.record(),project='other')
  self.assertEqual(self.k.get('other','dataset','rules','rules')['body']['purpose'],'reference')
  self.save('dataset','rules',{'title':'private','scope':'project','purpose':'reference'})
  with self.assertRaises(ValueError):self.k.get('other','dataset','rules','rules',revision=1)
 def test_confirmation_not_inferred_from_model_and_preview_is_pure(self):
  self.dataset(purpose='model');self.schema();before=(self.root/'data/workspace.sqlite3').read_bytes()
  self.k.preview('owner','record','rules','x',self.record(),2);self.assertEqual(before,(self.root/'data/workspace.sqlite3').read_bytes())
  with self.assertRaises(ValueError):self.save('record','x',self.record(status='confirmed'))
  self.save('record','x',self.record(status='confirmed'),owner_confirmed=True)
 def test_conflict_and_preview_tampering_and_exact_replay(self):
  self.dataset();self.schema();args=dict(project='owner',kind='record',dataset_id='rules',object_id='a',body=self.record(),baseline=2);p=self.k.preview(**args);save={**args,'preview_fingerprint':p['preview_fingerprint'],'operation_key':'fixed'};a=self.k.save(**save);self.assertEqual(self.k.save(**save),a)
  with self.assertRaises(ValueError):self.k.save(**{**save,'body':self.record(2)})
  with self.assertRaises(ValueError):self.k.save(**{**save,'operation_key':'new'})
 def test_schema_types_queries_and_withdrawal(self):
  self.dataset();self.schema()
  for row in (self.record(True),self.record(21),self.record(values={'oops':1}),self.record(schema_revision=99)):
   with self.assertRaises(ValueError):self.save('record','bad',row)
  self.save('record','a',self.record(2));self.save('record','b',self.record(4))
  hits=self.k.query('other','rules',record_type='growth',filters=[{'field':'level','op':'gte','value':3}]);self.assertEqual([r['object_id'] for r in hits['records']],['b'])
  with self.assertRaises(ValueError):self.k.query('other','rules',filters=[{'field':'level','op':'sql','value':'1=1'}])
  self.save('record','a',self.record(2,status='withdrawn'));self.assertEqual(len(self.k.query('owner','rules')['records']),1);self.assertEqual(self.k.get('owner','record','rules','a',1)['body']['status'],'candidate')
 def test_evidence_exact_revision_fingerprint_and_scope(self):
  self.dataset();self.schema();src={'research_source_id':'ref','title':'合成出处','media_type':'article','binding':{'kind':'url','locator':'https://example.invalid/a'},'scope':'global'};self.w.evidence.register(src,0,'source',False)
  source=self.w.evidence.get('ref','owner');binding={'source_id':'ref','source_revision':1,'source_version_fingerprint':digest(encode(source['source'])),'field':'level','position':{'type':'web_anchor','anchor':'levels'}}
  self.save('record','a',self.record(evidence=[binding]));bad=copy.deepcopy(binding);bad['source_version_fingerprint']='0'*64
  with self.assertRaises(ValueError):self.save('record','b',self.record(evidence=[bad]))
  src['scope']='project';src['owner_project']='owner';src['research_source_id']='private';src['binding']['locator']='https://example.invalid/private';self.w.evidence.register(src,0,'private',False);binding['source_id']='private';binding['source_version_fingerprint']=digest(encode(self.w.evidence.get('private','owner')['source']))
  with self.assertRaises(ValueError):self.save('record','leak',self.record(evidence=[binding]))
 def test_exact_relations_and_stale_endpoint_reporting(self):
  self.dataset();self.schema();a=self.save('record','a',self.record());b=self.save('record','b',self.record(2));endpoint=lambda name,r:{'dataset_id':'rules','record_id':name,'revision':r['revision'],'fingerprint':r['fingerprint']};relation={'relation_type':'depends_on','from':endpoint('a',a),'to':endpoint('b',b),'status':'candidate'}
  self.save('relation','a-b',relation);self.assertEqual(len(self.k.relations('owner','rules','a')['relations']),1);self.save('record','b',self.record(3));report=self.k.validate('owner','rules');self.assertTrue(any(e['code']=='superseded_endpoint' for e in report['warnings']))
  relation['to']['fingerprint']='0'*64
  with self.assertRaises(ValueError):self.save('relation','bad',relation)
 def test_json_import_atomic_errors_duplicates_and_replay(self):
  self.dataset();self.schema();content=json.dumps([{'id':'a','body':self.record()},{'id':'b','body':self.record(99)}]);args=dict(project='owner',dataset_id='rules',baseline=2,format='json',content=content)
  p=self.k.import_preview(**args);self.assertFalse(p['valid']);self.assertTrue(p['errors']);
  with self.assertRaises(ValueError):self.k.import_commit(**args,preview_fingerprint=p['preview_fingerprint'],operation_key='bad')
  self.assertEqual(self.k.query('owner','rules')['records'],[])
  args['content']=json.dumps([{'id':'a','body':self.record()},{'id':'b','body':self.record(2)}]);p=self.k.import_preview(**args);s={**args,'preview_fingerprint':p['preview_fingerprint'],'operation_key':'batch'};r=self.k.import_commit(**s);self.assertEqual(r['count'],2);self.assertEqual(self.k.import_commit(**s),r)
  args.update(baseline=r['dataset_revision'],content=json.dumps([{'id':'a','body':self.record()},{'id':'a','body':self.record(2)}]));self.assertFalse(self.k.import_preview(**args)['valid'])
 def test_csv_file_mapping_hash_and_changed_input(self):
  self.dataset();self.schema();file=self.root/'rules.csv';file.write_text('key,lvl\na,3\nb,4\n');args=dict(project='owner',dataset_id='rules',baseline=2,format='csv',path=str(file),field_mapping={'key':'id','lvl':'level'},record_type='growth',schema_revision=1,expected_sha256=hashlib.sha256(file.read_bytes()).hexdigest());p=self.k.import_preview(**args);self.assertTrue(p['valid']);file.write_text('key,lvl\na,5\n')
  with self.assertRaises(ValueError):self.k.import_commit(**args,preview_fingerprint=p['preview_fingerprint'],operation_key='changed')
 def test_import_path_and_size_restrictions(self):
  self.dataset();self.schema()
  for kw in ({'content':'x'*1_048_577},{'path':'/etc/passwd'},{'path':str(self.root/'missing')},{'content':'[]','path':'/etc/passwd'}):
   with self.assertRaises(ValueError):self.k.import_preview(project='owner',dataset_id='rules',baseline=2,format='json',**kw)
 def test_import_transaction_rolls_back_after_late_write_failure(self):
  self.dataset();self.schema();args=dict(project='owner',dataset_id='rules',baseline=2,format='json',content=json.dumps([{'id':'a','body':self.record()},{'id':'b','body':self.record(2)}]));p=self.k.import_preview(**args);insert=self.k._insert
  def fail_second(db,kind,dataset,oid,body,commit,provenance=None):
   if oid=='b':raise ValueError('injected write failure')
   return insert(db,kind,dataset,oid,body,commit,provenance=provenance)
  with patch.object(self.k,'_insert',side_effect=fail_second),self.assertRaises(ValueError):self.k.import_commit(**args,preview_fingerprint=p['preview_fingerprint'],operation_key='batch')
  self.assertEqual(self.k.revision('rules'),2);self.assertEqual(self.k.query('owner','rules')['total'],0)
 def test_csv_reports_conversion_errors_and_successful_import(self):
  self.dataset();self.schema();args=dict(project='owner',dataset_id='rules',baseline=2,format='csv',content='key,lvl\na,nope\n',field_mapping={'key':'id','lvl':'level'},record_type='growth',schema_revision=1);p=self.k.import_preview(**args);self.assertFalse(p['valid']);self.assertTrue(p['errors'])
  args['content']='key,lvl\na,3\nb,4\n';p=self.k.import_preview(**args);self.k.import_commit(**args,preview_fingerprint=p['preview_fingerprint'],operation_key='csv');self.assertEqual(self.k.query('owner','rules')['total'],2)
 def test_schema7_migration_preserves_data_and_rolls_back_failure(self):
  from novel_store import Store
  from knowledge_models import schema
  with self.w.store.connection(write=True) as db:
   db.execute('DROP TABLE knowledge_versions');db.execute('PRAGMA user_version=7');db.execute("INSERT INTO checkpoints VALUES('sample',1,'task','summary','next','[]','stamp')")
  with patch('knowledge_models.schema',side_effect=ValueError('migration fault')):
   with self.assertRaises(ValueError):Store(self.root/'data')
  with self.w.store.connection() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],7)
  store=Store(self.root/'data')
  with store.connection() as db:
   self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8);self.assertEqual(db.execute('SELECT task FROM checkpoints').fetchone()[0],'task')
 def test_world_and_tool_structures_use_same_import_api(self):
  examples=Path(__file__).resolve().parents[1]/'config/schemas'
  for name in ('world','tool'):
   sample=json.loads((examples/(name+'.json')).read_text());dataset=sample['dataset_id'];self.save('dataset',dataset,sample['dataset'],dataset=dataset);self.save('schema',sample['record_type'],sample['schema'],dataset=dataset);args=dict(project='owner',dataset_id=dataset,baseline=2,format='json',content=json.dumps(sample['records']));p=self.k.import_preview(**args);self.assertTrue(p['valid'],p);self.k.import_commit(**args,preview_fingerprint=p['preview_fingerprint'],operation_key=name);self.assertEqual(self.k.query('other',dataset)['total'],1)
 def test_schema_constraints_are_typed_and_finite(self):
  self.dataset()
  for body in ({'fields':{'name':{'type':'string','minimum':1}}},{'fields':{'level':{'type':'integer','enum':['high']}}},{'fields':{'score':{'type':'number','maximum':float('inf')}}}):
   with self.assertRaises(ValueError):self.save('schema','bad',body)
 def test_explicit_story_project_uses_knowledge_without_resuming_novel(self):
  from tests.support import create_story
  from knowledge_api import workspace,execute
  story=create_story(self.root/'story','sample-story');raw=json.loads(self.config.read_text());raw['projects']={'sample-story':str(story)};self.config.write_text(json.dumps(raw));w=workspace();args={'project':'sample-story','dataset_id':'story-model','body':{'title':'合成模型','scope':'project','purpose':'model'},'baseline':0};p=execute(w,'dataset_preview',args);r=execute(w,'dataset_save',{**args,'preview_fingerprint':p['preview_fingerprint'],'operation_key':'story'});self.assertEqual(r['revision'],1);self.assertNotIn('sample-story',ResearchWorkspace(profile='workspace').allowed)
 def test_parallel_preview_commits_reject_stale_baseline(self):
  from concurrent.futures import ThreadPoolExecutor
  self.dataset();self.schema()
  # Previews share a baseline; concurrent writes must leave exactly one commit.
  args1=dict(project='owner',kind='record',dataset_id='rules',object_id='a',body=self.record(),baseline=2);args2={**args1,'object_id':'b'};p1=self.k.preview(**args1);p2=self.k.preview(**args2)
  def commit(args,p):
   try:return self.k.save(**args,preview_fingerprint=p['preview_fingerprint'],operation_key=args['object_id'])
   except ValueError:return None
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda pair:commit(*pair),[(args1,p1),(args2,p2)]))
  self.assertEqual(sum(r is not None for r in results),1);self.assertEqual(self.k.query('owner','rules')['total'],1)
 def test_imported_records_expose_input_provenance(self):
  self.dataset();self.schema();text=json.dumps([{'id':'a','body':self.record()}]);args=dict(project='owner',dataset_id='rules',baseline=2,format='json',content=text);p=self.k.import_preview(**args);self.k.import_commit(**args,preview_fingerprint=p['preview_fingerprint'],operation_key='provenance');row=self.k.get('other','record','rules','a');self.assertEqual(row['provenance']['input_sha256'],hashlib.sha256(text.encode()).hexdigest());self.assertEqual(row['provenance']['row_index'],1)
 def test_csv_source_reused_and_changed_file_marked_stale(self):
  self.dataset();self.schema();file=self.root/'source.csv';file.write_text('level\n1\n');src={'research_source_id':'csv-source','title':'合成CSV来源','media_type':'text','binding':{'kind':'local_file','locator':str(file)},'scope':'global','expected_fingerprint':hashlib.sha256(file.read_bytes()).hexdigest()};self.w.evidence.register(src,0,'csv-source',False);s=self.w.evidence.get('csv-source','owner');binding={'source_id':'csv-source','source_revision':1,'source_version_fingerprint':s['version_fingerprint'],'field':'level','position':{'type':'text_range','line_start':2,'line_end':2}};self.save('record','a',self.record(evidence=[binding]));file.write_text('level\n2\n');row=self.k.get('owner','record','rules','a');self.assertTrue(row['evidence_states'][0]['stale'])
