"""Project-scoped versioned datasets. All writes are previewed and transactional."""
import json
from novel_store import identifier,digest,now
from novel_evidence import encode
from knowledge_models import MODELS,validate_values

class Knowledge:
 def __init__(self,workspace):self.w=workspace;self.store=workspace.store
 def revision(self,dataset_id,db=None):
  identifier(dataset_id)
  if db is None:
   with self.store.connection() as conn:return self.revision(dataset_id,conn)
  return db.execute('SELECT COALESCE(MAX(commit_revision),0) FROM knowledge_versions WHERE dataset_id=?',(dataset_id,)).fetchone()[0]
 def _row(self,db,kind,dataset,oid,revision=0,snapshot=0):
  identifier(dataset);identifier(oid)
  if kind not in MODELS:raise ValueError('未知知识对象类型')
  query='SELECT * FROM knowledge_versions WHERE kind=? AND dataset_id=? AND object_id=?';args=[kind,dataset,oid]
  if revision:query+=' AND revision=?';args.append(revision)
  if snapshot:query+=' AND commit_revision<=?';args.append(snapshot)
  row=db.execute(query+' ORDER BY revision DESC LIMIT 1',args).fetchone()
  if row is None:raise ValueError('知识对象或版本不存在')
  result=dict(row);result['body']=json.loads(row['body']);result['provenance']=json.loads(row['provenance']);return result
 def _access(self,db,project,dataset,write=False):
  self.w.project(project);row=self._row(db,'dataset',dataset,dataset);meta=row['body']
  if meta['scope']=='project' and meta['owner_project']!=project or write and meta['owner_project']!=project:raise ValueError('数据集不属于当前项目或只允许创建项目维护')
  return row
 def _evidence(self,db,project,meta,body):
  for binding in body['evidence']:
   _,source,_=self.w.evidence.access(db,binding['source_id'],project,binding['source_revision'])
   if meta['scope']=='global' and source['scope']!='global':raise ValueError('共享数据集不能引用项目私有来源')
   if digest(encode(source))!=binding['source_version_fingerprint']:raise ValueError('来源版本元数据指纹不符')
   if binding['field']!='*' and binding['field'] not in body['values']:raise ValueError('证据字段不存在')
 def _prepare(self,db,project,kind,dataset,oid,body,owner_confirmed=False):
  self.w.project(project);identifier(dataset);identifier(oid)
  if kind not in MODELS:raise ValueError('未知知识对象类型')
  normalized=MODELS[kind].model_validate(body).model_dump(mode='json',by_alias=True)
  if len(encode(normalized).encode())>65536:raise ValueError('单条记录超过64KiB')
  if normalized.get('status')=='confirmed' and owner_confirmed is not True:raise ValueError('confirmed必须明确owner_confirmed，不由用途推断')
  if kind=='dataset':
   if oid!=dataset:raise ValueError('数据集对象ID须等于dataset_id')
   if self.revision(dataset,db):
    old=self._access(db,project,dataset,True)['body']
    if old['purpose']!=normalized['purpose'] or old['scope']=='project' and normalized['scope']=='global':raise ValueError('不得改变用途或将私有历史公开；请另建数据集')
   return {**normalized,'owner_project':project}
  meta=self._access(db,project,dataset,True)['body']
  if kind=='record':
   schema=self._row(db,'schema',dataset,normalized['record_type'],normalized['schema_revision']);validate_values(schema['body'],normalized['values']);self._evidence(db,project,meta,normalized)
   from prompt_library import validate_prompt_record
   validate_prompt_record(self,db,project,meta,oid,normalized)
  if kind=='relation':
   endpoints=[]
   for key in ('from','to'):
    e=normalized[key];target_meta=self._access(db,project,e['dataset_id'])['body']
    if meta['scope']=='global' and target_meta['scope']!='global':raise ValueError('共享关系不能指向私有数据')
    row=self._row(db,'record',e['dataset_id'],e['record_id'],e['revision'])
    if row['fingerprint']!=e['fingerprint']:raise ValueError('关系端点指纹不符')
    if row['body']['status']=='withdrawn':raise ValueError('关系不能绑定已撤回记录')
    endpoints.append(row)
   first=endpoints[0];structure=self._row(db,'schema',first['dataset_id'],first['body']['record_type'],first['body']['schema_revision'])
   if normalized['relation_type'] not in structure['body']['allowed_relations']:raise ValueError('结构未允许该关系类型')
  return normalized
 def _preview(self,db,project,kind,dataset_id,object_id,body,baseline,owner_confirmed=False):
  if type(baseline) is not int or baseline<0 or self.revision(dataset_id,db)!=baseline:raise ValueError('数据集基线冲突')
  normalized=self._prepare(db,project,kind,dataset_id,object_id,body,owner_confirmed)
  try:old=self._row(db,kind,dataset_id,object_id)
  except ValueError:old=None
  request={'project':project,'kind':kind,'dataset_id':dataset_id,'object_id':object_id,'body':normalized,'baseline':baseline,'owner_confirmed':owner_confirmed}
  return {'baseline':baseline,'object_revision':old['revision'] if old else 0,'before':old['body'] if old else None,'after':normalized,'change':'unchanged' if old and old['body']==normalized else 'update' if old else 'add','preview_fingerprint':digest(encode(request)),'fact_verification':'not_verified','canon':False}
 def preview(self,project,kind,dataset_id,object_id,body,baseline,owner_confirmed=False):
  with self.store.connection() as db:return self._preview(db,project,kind,dataset_id,object_id,body,baseline,owner_confirmed)
 def _insert(self,db,kind,dataset,oid,body,commit,provenance=None):
  try:revision=self._row(db,kind,dataset,oid)['revision']+1
  except ValueError:revision=1
  fp=digest(encode(body));db.execute('INSERT INTO knowledge_versions VALUES(?,?,?,?,?,?,?,?,?)',(kind,dataset,oid,revision,commit,encode(body),fp,now(),encode(provenance or {})))
  return {'kind':kind,'dataset_id':dataset,'object_id':oid,'revision':revision,'dataset_revision':commit,'fingerprint':fp}
 def save(self,project,kind,dataset_id,object_id,body,baseline,preview_fingerprint,operation_key,owner_confirmed=False):
  request={'kind':kind,'dataset':dataset_id,'id':object_id,'body':body,'baseline':baseline,'preview_fingerprint':preview_fingerprint,'owner_confirmed':owner_confirmed};namespace='knowledge:'+project
  with self.store.connection(write=True) as db:
   self.w.project(project)
   if self.revision(dataset_id,db):self._access(db,project,dataset_id,True)
   previous=self.w.evidence.retry(db,namespace,operation_key,request)
   if previous:return previous
   p=self._preview(db,project,kind,dataset_id,object_id,body,baseline,owner_confirmed)
   if p['preview_fingerprint']!=preview_fingerprint:raise ValueError('预览指纹不一致')
   result=self._insert(db,kind,dataset_id,object_id,p['after'],baseline+1);self.w.evidence.operation(db,namespace,operation_key,request,result);return result
 def get(self,project,kind,dataset_id,object_id,revision=0,dataset_revision=0,expected_fingerprint=''):
  with self.store.connection() as db:
   self._access(db,project,dataset_id);self._snapshot(db,dataset_id,dataset_revision)
   row=self._row(db,kind,dataset_id,object_id,revision,dataset_revision)
   if expected_fingerprint and row['fingerprint']!=expected_fingerprint:raise ValueError('记录指纹不符')
   result=self._decorate(db,project,row);result['current_dataset_revision']=self.revision(dataset_id,db);return result
 def _decorate(self,db,project,row):
  row=dict(row);row['dataset_revision']=row.pop('commit_revision');row['structure_valid']=True;row['fact_verification']='not_verified';row['canon']=False
  if row['kind']=='record':
   body=row['body'];structure=self._row(db,'schema',row['dataset_id'],body['record_type'],body['schema_revision']);row['schema_fingerprint']=structure['fingerprint'];states=[]
   for e in body['evidence']:
    source,_,_=self.w.evidence.access(db,e['source_id'],project,e['source_revision']);current=self.w.evidence.get(e['source_id'],project,e['source_revision']);states.append({'source_id':e['source_id'],'revision':e['source_revision'],'superseded':source['revision']!=e['source_revision'],'stale':current['stale'],'source_state':current['source_state'],'evidence_reader':current['evidence_reader']})
   row['evidence_states']=states
  return row
 def _snapshot(self,db,dataset,revision):
  if type(revision) is not int or revision<0 or revision>self.revision(dataset,db):raise ValueError('数据集快照版本无效')
 def _latest(self,db,kind,dataset,snapshot=0):
  rows=db.execute('SELECT * FROM knowledge_versions WHERE kind=? AND dataset_id=? AND commit_revision<=? ORDER BY object_id,revision DESC',(kind,dataset,snapshot or self.revision(dataset,db))).fetchall();seen=set();result=[]
  for row in rows:
   if row['object_id'] not in seen:
    seen.add(row['object_id']);item=dict(row);item['body']=json.loads(item['body']);item['provenance']=json.loads(item['provenance']);result.append(item)
  return result
 def query(self,project,dataset_id,dataset_revision=0,record_type='',filters=None,offset=0,limit=20,include_withdrawn=False):
  if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50:raise ValueError('分页无效')
  filters=filters or []
  if not isinstance(filters,list) or len(filters)>10:raise ValueError('最多10个过滤条件')
  for f in filters:
   if not isinstance(f,dict) or set(f)!={'field','op','value'} or f['op'] not in ('eq','ne','gt','gte','lt','lte','in'):raise ValueError('过滤字段或操作符无效')
   identifier(f['field'])
   if f['op']=='in' and (not isinstance(f['value'],list) or len(f['value'])>50):raise ValueError('in最多50值')
  with self.store.connection() as db:
   self._access(db,project,dataset_id);self._snapshot(db,dataset_id,dataset_revision);records=[]
   for row in self._latest(db,'record',dataset_id,dataset_revision):
    body=row['body']
    if record_type and body['record_type']!=record_type or not include_withdrawn and body['status']=='withdrawn':continue
    match=True
    for f in filters:
     if f['field'] not in body['values']:match=False;break
     left=body['values'][f['field']];right=f['value'];op=f['op']
     try:
      compatible=type(left)==type(right) or type(left) in (int,float) and type(right) in (int,float)
      ok=any(type(left)==type(v) and left==v for v in right) if op=='in' else compatible and {'eq':lambda:left==right,'ne':lambda:left!=right,'gt':lambda:left>right,'gte':lambda:left>=right,'lt':lambda:left<right,'lte':lambda:left<=right}[op]()
     except TypeError:ok=False
     if not ok:match=False;break
    if match:records.append(row)
   return {'records':[self._decorate(db,project,r) for r in records[offset:offset+limit]],'total':len(records),'dataset_revision':dataset_revision or self.revision(dataset_id,db),'next_offset':offset+limit if offset+limit<len(records) else None}
 def relations(self,project,dataset_id,record_id='',direction='both',offset=0,limit=20):
  if direction not in ('both','incoming','outgoing') or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50:raise ValueError('关系查询范围无效')
  with self.store.connection() as db:
   self._access(db,project,dataset_id);rows=[]
   for row in self._latest(db,'relation',dataset_id):
    b=row['body']
    if b['status']=='withdrawn':continue
    keys=('from','to') if direction=='both' else ('from',) if direction=='outgoing' else ('to',)
    if not record_id or any(b[k]['record_id']==record_id and b[k]['dataset_id']==dataset_id for k in keys):rows.append(row)
   return {'relations':rows[offset:offset+limit],'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None,'notice':'仅本数据集显式关系；不推断传递依赖或计算影响'}
 def validate(self,project,dataset_id):
  errors=[];warnings=[]
  with self.store.connection() as db:
   meta=self._access(db,project,dataset_id)['body']
   for kind in ('record','relation'):
    for row in self._latest(db,kind,dataset_id):
     body=row['body']
     if body['status']=='withdrawn':continue
     try:
      if kind=='record':
       schema=self._row(db,'schema',dataset_id,body['record_type'],body['schema_revision']);validate_values(schema['body'],body['values']);self._evidence(db,project,meta,body)
       from prompt_library import validate_prompt_record
       validate_prompt_record(self,db,project,meta,row['object_id'],body)
       if not body['evidence']:warnings.append({'id':row['object_id'],'code':'missing_evidence'})
       for e in body['evidence']:
        source,_,_=self.w.evidence.access(db,e['source_id'],project,e['source_revision'])
        state=self.w.evidence.get(e['source_id'],project,e['source_revision'])
        if state['stale']:warnings.append({'id':row['object_id'],'code':'superseded_or_changed_source'})
      else:
       for key in ('from','to'):
        e=body[key];self._access(db,project,e['dataset_id']);exact=self._row(db,'record',e['dataset_id'],e['record_id'],e['revision']);latest=self._row(db,'record',e['dataset_id'],e['record_id'])
        if exact['fingerprint']!=e['fingerprint']:raise ValueError('关系指纹不符')
        if latest['revision']!=e['revision']:warnings.append({'id':row['object_id'],'code':'superseded_endpoint'})
     except ValueError as exc:errors.append({'id':row['object_id'],'code':'invalid_reference','message':str(exc)})
   return {'valid':not errors,'errors':errors[:100],'warnings':warnings[:100],'total_errors':len(errors),'total_warnings':len(warnings),'fact_verification':'not_verified','formulas':'not_executed'}
 def import_preview(self,**args):
  from knowledge_import import preview
  with self.store.connection() as db:return preview(self,db,**args)
 def import_commit(self,preview_fingerprint,operation_key,**args):
  from knowledge_import import preview
  namespace='knowledge-import:'+args.get('project','');request={'args':args,'preview_fingerprint':preview_fingerprint}
  with self.store.connection(write=True) as db:
   self._access(db,args['project'],args['dataset_id'],True)
   old=self.w.evidence.retry(db,namespace,operation_key,request)
   if old:return old
   p=preview(self,db,**args)
   if not p['valid'] or p['preview_fingerprint']!=preview_fingerprint:raise ValueError('导入校验失败或预览变化')
   commit=args['baseline']+1;results=[]
   for index,r in enumerate(p.pop('_rows'),1):results.append(self._insert(db,'record',args['dataset_id'],r['id'],r['body'],commit,provenance={'input_sha256':p['input_sha256'],'format':args['format'],'row_index':index}))
   result={'dataset_revision':commit,'count':len(results),'records':results,'input_sha256':p['input_sha256']};self.w.evidence.operation(db,namespace,operation_key,request,result);return result
 def datasets(self,project,dataset_id='',revision=0,dataset_revision=0):
  self.w.project(project)
  with self.store.connection() as db:
   ids=[r[0] for r in db.execute("SELECT DISTINCT dataset_id FROM knowledge_versions WHERE kind='dataset' ORDER BY dataset_id")];rows=[]
   for dataset in ids:
    try:row=self._access(db,project,dataset)
    except ValueError:continue
    rows.append({'dataset_id':dataset,'dataset_revision':self.revision(dataset,db),'definition':row['body']})
   if len(rows)>100:raise ValueError('可访问数据集超过100，须按明确dataset_id读取')
   return {'datasets':rows,'total':len(rows)}
 def dispatch(self,operation,params):
  if operation not in {'preview','save','get','query','relations','validate','import_preview','import_commit'}:raise ValueError('未知知识操作')
  result=getattr(self,operation)(**params)
  if operation=='import_preview':result={k:v for k,v in result.items() if k!='_rows'}
  return result
