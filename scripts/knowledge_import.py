"""Bounded CSV/JSON transport, parsing, and all-or-nothing preview preparation."""
import csv,hashlib,io,json,os,stat
from pathlib import Path
from novel_store import identifier,digest
from novel_evidence import encode
MAX_BYTES=1_048_576

def read_input(w,content='',path='',expected_sha256=''):
 if bool(content)==bool(path):raise ValueError('须且仅须提供content或许可目录path')
 if path:
  p=Path(path).expanduser()
  if not p.is_absolute() or p.is_symlink():raise ValueError('仅接受许可目录普通文件绝对路径')
  resolved=p.resolve()
  if not any(resolved.is_relative_to(Path(root).resolve()) for root in w.research_roots):raise ValueError('文件不在research_roots许可目录')
  try:fd=os.open(resolved,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
  except OSError:raise ValueError('导入文件不可读') from None
  with os.fdopen(fd,'rb') as stream:
   before=os.fstat(stream.fileno())
   if not stat.S_ISREG(before.st_mode):raise ValueError('只允许普通文件')
   raw=stream.read(MAX_BYTES+1);after=os.fstat(stream.fileno())
  if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns) or resolved.stat().st_ino!=before.st_ino:raise ValueError('文件读取期间变化')
  if p.resolve()!=resolved:raise ValueError('文件路径变化')
 else:
  if not isinstance(content,str):raise ValueError('content须为UTF-8文本')
  raw=content.encode('utf-8')
 if len(raw)>MAX_BYTES:raise ValueError('导入超过1MiB')
 fp=hashlib.sha256(raw).hexdigest()
 if expected_sha256 and fp!=expected_sha256:raise ValueError('输入SHA-256不符')
 if path and not expected_sha256:raise ValueError('文件导入须明确expected_sha256')
 return raw.decode('utf-8-sig'),fp

def preview(k,db,project,dataset_id,baseline,format,content='',path='',expected_sha256='',field_mapping=None,record_type='',schema_revision=0,evidence=None,owner_confirmed=False):
 k._access(db,project,dataset_id,True)
 if type(baseline) is not int or k.revision(dataset_id,db)!=baseline:raise ValueError('数据集基线冲突')
 text,fp=read_input(k.w,content,path,expected_sha256);errors=[];rows=[];seen=set();changes=[]
 if format=='json':
  values=json.loads(text)
  if not isinstance(values,list):raise ValueError('JSON导入须为记录数组')
 elif format=='csv':
  if not isinstance(field_mapping,dict) or 'id' not in field_mapping.values() or len(set(field_mapping.values()))!=len(field_mapping):raise ValueError('CSV须明确唯一字段映射及id列')
  structure=k._row(db,'schema',dataset_id,record_type,schema_revision)['body'];reader=csv.DictReader(io.StringIO(text));headers=reader.fieldnames or []
  if len(headers)!=len(set(headers)) or set(headers)!=set(field_mapping):raise ValueError('CSV列须与显式映射完全一致')
  values=[]
  for number,row in enumerate(reader,2):
   if number>501:raise ValueError('导入最多500行')
   try:
    if None in row or any(v is None for v in row.values()):raise ValueError('CSV行列数不一致')
    fields={};oid=''
    for col,field in field_mapping.items():
     if field=='id':oid=row[col];continue
     if field not in structure['fields']:raise ValueError('映射字段不在结构中')
     spec=structure['fields'][field];value=row[col]
     if value=='' and not spec['required']:continue
     if spec['type']=='integer':value=int(value)
     elif spec['type']=='number':value=float(value)
     elif spec['type']=='boolean':
      if value not in ('true','false'):raise ValueError('布尔CSV须true/false')
      value=value=='true'
     fields[field]=value
    values.append({'id':oid,'body':{'record_type':record_type,'schema_revision':schema_revision,'values':fields,'evidence':evidence or []}})
   except (ValueError,TypeError) as exc:errors.append({'row':number,'message':str(exc)})
 else:raise ValueError('仅支持csv/json')
 if len(values)>500 or not values and not errors:raise ValueError('导入须1–500条记录')
 for number,value in enumerate(values,1):
  try:
   if not isinstance(value,dict) or set(value)!={'id','body'}:raise ValueError('记录须id/body')
   oid=identifier(value['id'])
   if oid in seen:raise ValueError('重复业务ID')
   seen.add(oid);p=k._preview(db,project,'record',dataset_id,oid,value['body'],baseline,owner_confirmed);rows.append({'id':oid,'body':p['after']});changes.append({'id':oid,'change':p['change'],'before':p['before'],'after':p['after']})
  except (ValueError,TypeError,KeyError) as exc:errors.append({'row':number,'message':str(exc)})
 token={'project':project,'dataset_id':dataset_id,'baseline':baseline,'input_sha256':fp,'format':format,'field_mapping':field_mapping,'record_type':record_type,'schema_revision':schema_revision,'evidence':evidence,'owner_confirmed':owner_confirmed,'changes':changes,'errors':errors}
 return {'valid':not errors,'baseline':baseline,'input_sha256':fp,'changes':changes,'errors':errors,'preview_fingerprint':digest(encode(token)),'_rows':rows,'fact_verification':'not_verified'}
