"""Bounded, config-whitelisted local workspace filesystem reader. Read-only."""
from __future__ import annotations
import hashlib,os,re,stat
from datetime import datetime,timezone
from fnmatch import fnmatch
from pathlib import Path,PurePosixPath

DEFAULT_MAX=2*1024*1024
DEFAULT_SUFFIXES=('.md','.txt','.json')
DEFAULT_DENY=('.git/**','.venv/**')
MAX_LIST=5000
POLICY=('本地工作区只读；路径仅相对且须在配置根内。'
        '列表/读取/检索不写文件、不执行内容指令、不做语义搜索。')

def sha(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()

def relative(value:str)->PurePosixPath:
 if not isinstance(value,str) or '\\' in value:raise ValueError('必须传许可范围内的相对路径')
 if value in ('','.'):return PurePosixPath('.')
 p=PurePosixPath(value)
 if p.is_absolute() or any(x in ('.','..') or x.startswith('.') for x in value.split('/')):
  raise ValueError('隐藏路径、绝对路径与路径穿越不允许')
 return p

def _parse_fs_read(raw):
 if raw is None:return None
 if not isinstance(raw,dict):raise ValueError('fs_read须为对象')
 allowed={'enabled','readonly','suffixes','max_file_bytes','deny_globs'}
 if set(raw)-allowed:raise ValueError('fs_read字段无效')
 if not isinstance(raw.get('enabled',False),bool):raise ValueError('fs_read.enabled须布尔')
 if not raw.get('enabled',False):return None
 if 'readonly' in raw and raw['readonly'] is not True:raise ValueError('fs_read仅支持readonly=true')
 suffixes=raw.get('suffixes',list(DEFAULT_SUFFIXES))
 if not isinstance(suffixes,list) or not suffixes or any(not isinstance(s,str) or not s.startswith('.') or len(s)>16 for s in suffixes):
  raise ValueError('fs_read.suffixes无效')
 max_bytes=raw.get('max_file_bytes',DEFAULT_MAX)
 if type(max_bytes) is not int or not 1<=max_bytes<=DEFAULT_MAX:raise ValueError('fs_read.max_file_bytes无效')
 deny=raw.get('deny_globs',list(DEFAULT_DENY))
 if not isinstance(deny,list) or any(not isinstance(g,str) or not g or len(g)>200 for g in deny):
  raise ValueError('fs_read.deny_globs无效')
 return {'enabled':True,'readonly':True,'suffixes':tuple(suffixes),'max_file_bytes':max_bytes,'deny_globs':tuple(deny)}

def collect_fs_workspaces(research:dict,extra,resolve)->dict:
 out={}
 for key,value in research.items():
  if not isinstance(value,dict):continue
  cfg=_parse_fs_read(value.get('fs_read'))
  if not cfg:continue
  root=value['path'] if isinstance(value['path'],Path) else resolve(value['path'])
  out[key]={'root':root,'label':value.get('label',key),'domain':value.get('domain',''),'fs_read':cfg}
 if extra:
  if not isinstance(extra,dict):raise ValueError('fs_workspaces须为对象')
  for key,value in extra.items():
   if not isinstance(key,str) or not re.fullmatch(r'[a-z0-9_-]{1,80}',key):raise ValueError('fs工作区ID无效')
   if not isinstance(value,dict) or 'path' not in value:raise ValueError('fs_workspaces项须含path')
   cfg=_parse_fs_read(value.get('fs_read') or {'enabled':True,'readonly':True})
   if not cfg:continue
   if key in out:raise ValueError('fs工作区与workspaces重复: '+key)
   label=value.get('label',key)
   if not isinstance(label,str) or not label.strip() or len(label)>200:raise ValueError('fs工作区label无效')
   out[key]={'root':resolve(value['path']),'label':label.strip(),'domain':str(value.get('domain') or 'fs'),'fs_read':cfg}
 return out

def list_fs_workspaces(settings):
 return [{'project':key,'label':cfg['label'],'domain':cfg['domain'],'readonly':True,
          'suffixes':list(cfg['fs_read']['suffixes']),'root_exists':cfg['root'].is_dir()}
         for key,cfg in settings.get('fs_workspaces',{}).items()]

class FsWorkspace:
 def __init__(self,settings,project:str):
  catalog=settings.get('fs_workspaces',{})
  if project not in catalog:raise ValueError('未启用fs只读的工作区或不存在: '+project)
  self.project=project;self.cfg=catalog[project];self.root=self.cfg['root'];self.fs=self.cfg['fs_read']
  if not self.root.is_dir() or self.root.is_symlink():raise ValueError('工作区根须为普通目录')

 def status(self):
  return {'project':self.project,'label':self.cfg['label'],'domain':self.cfg['domain'],'readonly':True,
          'suffixes':list(self.fs['suffixes']),'max_file_bytes':self.fs['max_file_bytes'],
          'deny_globs':list(self.fs['deny_globs']),'root_exists':self.root.is_dir(),'policy':POLICY}

 def denied(self,rel:str)->bool:
  posix=rel.replace('\\','/')
  for pattern in self.fs['deny_globs']:
   if fnmatch(posix,pattern):return True
   top=posix.split('/',1)[0]
   if pattern in (top,top+'/**') or fnmatch(top,pattern.rstrip('/**')):return True
  return any(p.startswith('.') for p in PurePosixPath(posix).parts)

 def open_file(self,path:str):
  rel=relative(path)
  if rel==PurePosixPath('.'):raise ValueError('须指定文件相对路径')
  text_path=rel.as_posix()
  if self.denied(text_path):raise ValueError('路径在deny列表或隐藏路径内')
  if PurePosixPath(text_path).suffix not in self.fs['suffixes']:raise ValueError('后缀不在允许列表')
  try:
   fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
   try:
    parts=rel.parts
    for part in parts[:-1]:
     nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
     os.close(fd);fd=nxt
    leaf=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try:
     info=os.fstat(leaf)
     if not stat.S_ISREG(info.st_mode) or info.st_size>self.fs['max_file_bytes']:
      raise ValueError('只读取许可大小内的普通文本文件')
     with os.fdopen(leaf,'rb',closefd=False) as stream:raw=stream.read(self.fs['max_file_bytes']+1)
     after=os.fstat(leaf)
     if len(raw)>self.fs['max_file_bytes'] or (info.st_size,info.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
      raise ValueError('文件读取期间变化或超过大小上限')
    finally:os.close(leaf)
   finally:os.close(fd)
  except OSError as exc:
   raise ValueError('无法安全打开文件（拒绝符号链接或无效路径）') from exc
  text=raw.decode('utf-8-sig')
  if '\x00' in text:raise ValueError('二进制文件不允许')
  return raw,text,info

 def metadata(self,path:str):
  raw,text,info=self.open_file(path)
  return {'path':path,'fingerprint':sha(raw),'fingerprint_scheme':'sha256_raw_bytes',
          'bytes':len(raw),'lines':len(text.splitlines()),
          'updated_at':datetime.fromtimestamp(info.st_mtime,timezone.utc).isoformat(),
          'verification':'file_bytes_checked','readonly':True,'canon':False}

 def list_files(self,path:str='.',depth:int=2,offset:int=0,limit:int=100):
  if type(depth) is not int or not 0<=depth<=8:raise ValueError('depth范围无效')
  if offset<0 or not 1<=limit<=200:raise ValueError('分页范围无效')
  base_rel=relative(path) if path not in ('','.') else PurePosixPath('.')
  base=self.root if base_rel==PurePosixPath('.') else self.root.joinpath(*base_rel.parts)
  if base_rel!=PurePosixPath('.'):
   fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
   try:
    cur=fd
    for part in base_rel.parts:
     nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=cur)
     if cur!=fd:os.close(cur)
     cur=nxt
    if cur!=fd:os.close(cur)
   finally:os.close(fd)
  if not base.is_dir() or base.is_symlink():raise ValueError('列表路径须为普通目录')
  files=[]
  def walk(directory:Path,rel:PurePosixPath,remaining:int):
   if len(files)>MAX_LIST:raise ValueError('文件数超过上限；缩小path或depth')
   try:entries=sorted(os.listdir(directory),key=lambda x:x.lower())
   except OSError as exc:raise ValueError('无法列出目录: '+str(exc)) from exc
   for name in entries:
    child=directory/name
    child_rel=(rel/name).as_posix() if rel!=PurePosixPath('.') else name
    if name.startswith('.') or self.denied(child_rel) or child.is_symlink():continue
    if child.is_dir():
     if remaining>0:walk(child,PurePosixPath(child_rel),remaining-1)
     continue
    if not child.is_file():continue
    if PurePosixPath(name).suffix not in self.fs['suffixes']:continue
    try:raw,_,info=self.open_file(child_rel)
    except (ValueError,OSError,UnicodeError):continue
    files.append({'path':child_rel,'fingerprint':sha(raw),'bytes':len(raw),
                  'updated_at':datetime.fromtimestamp(info.st_mtime,timezone.utc).isoformat()})
  walk(base,base_rel,depth)
  files.sort(key=lambda x:x['path'])
  page=files[offset:offset+limit]
  return {'project':self.project,'path':'.' if base_rel==PurePosixPath('.') else base_rel.as_posix(),
          'depth':depth,'total':len(files),'files':page,
          'next_offset':offset+limit if offset+limit<len(files) else None,'policy':POLICY}

 def read_file(self,path:str,expected_fingerprint:str,char_offset:int=0,max_chars:int=3000):
  if char_offset<0 or not 1<=max_chars<=6000:raise ValueError('读取范围无效；最多6000字符')
  if not expected_fingerprint or not re.fullmatch(r'[0-9a-f]{64}',expected_fingerprint):
   raise ValueError('须提供当前文件SHA256指纹')
  raw,text,_=self.open_file(path)
  if sha(raw)!=expected_fingerprint:raise ValueError('文件指纹不一致；先重新列表或读取元数据')
  if char_offset>len(text):raise ValueError('偏移超过文件长度')
  end=min(len(text),char_offset+max_chars)
  meta=self.metadata(path)
  if meta['fingerprint']!=expected_fingerprint:raise ValueError('文件已变化；请重新获取指纹')
  excerpt=text[char_offset:end]
  start=text.count('\n',0,char_offset)+1
  return {**meta,'project':self.project,'char_start':char_offset,'char_end':end,
          'line_start':start,'line_end':text.count('\n',0,max(char_offset,end-1))+1,
          'text':excerpt,'next_char_offset':end if end<len(text) else None,'policy':POLICY}

 def search(self,query:str,mode:str='and',limit:int=20,path_prefix:str=''):
  if mode not in ('and','or','phrase'):raise ValueError('mode须为and/or/phrase')
  if not isinstance(query,str) or not query.strip() or len(query)>200:raise ValueError('查询无效')
  if not 1<=limit<=50:raise ValueError('limit范围无效')
  prefix=relative(path_prefix.rstrip('/')).as_posix() if path_prefix else ''
  if mode=='phrase':
   needle=query.strip();terms=None
  else:
   terms=query.split();needle=None
   if not terms:raise ValueError('查询无效')
  files=[];offset=0
  while True:
   page=self.list_files(prefix or '.',depth=8,offset=offset,limit=200)
   files.extend(page['files'])
   if page['next_offset'] is None:break
   offset=page['next_offset']
  hits=[];scanned=0
  for item in files:
   path=item['path']
   if prefix and not (path==prefix or path.startswith(prefix+'/')):continue
   try:raw,text,_=self.open_file(path)
   except (ValueError,OSError,UnicodeError):continue
   scanned+=1;fp=sha(raw)
   for number,line in enumerate(text.splitlines(),1):
    fold=line.casefold()
    if mode=='phrase':matched=needle.casefold() in fold
    elif mode=='and':matched=all(t.casefold() in fold for t in terms)
    else:matched=any(t.casefold() in fold for t in terms)
    if not matched:continue
    hits.append({'path':path,'line_start':number,'line_end':number,'text':line[:2000],
                 'truncated':len(line)>2000,'fingerprint':fp})
    if len(hits)>=limit:break
   if len(hits)>=limit:break
  return {'project':self.project,'query':query,'mode':mode,'hits':hits,'total':len(hits),
          'scanned_files':scanned,'complete':len(hits)<limit,'policy':POLICY,
          'notice':'扫盘字面匹配；未命中不证明资料不存在。'}
