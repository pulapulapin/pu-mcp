"""Optional PuCatch adapter: local transport and separately tracked research jobs."""
import hashlib
import ipaddress
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from novel_config import load_settings

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('拒绝采集服务重定向')

def public_url(value):
    if not isinstance(value,str) or len(value)>2000 or any(c in value for c in '\r\n\x00'):
        raise ValueError('需要公开HTTP/HTTPS链接')
    p=urlsplit(value)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
        raise ValueError('需要公开HTTP/HTTPS链接；不接受内嵌凭据')
    host=p.hostname.lower()
    if host in ('localhost','localhost.localdomain') or host.endswith(('.localhost','.local')):
        raise ValueError('采集来源不能是本机地址')
    try:ip=ipaddress.ip_address(host)
    except ValueError:ip=None
    if ip is not None and not ip.is_global:raise ValueError('采集来源不能是私有地址')
    return value

def scrub(value):
    return re.sub(r'sk-[A-Za-z0-9_-]+','[redacted]',str(value))[:500]

class Capture:
    def __init__(self):
        settings=load_settings()
        self.settings=settings
        self.config=settings['pucatch']
        self.directory=settings['data_dir']/'capture'
    def enabled(self):
        if not self.config.get('enabled'):raise ValueError('PuCatch未启用；配置可选pucatch后使用，小说功能不受影响')
    def request(self,route,payload=None,headers=None):
        from pucatch_client import request
        self.enabled()
        return request(self.config['base_url'],route,payload,headers)
    def status(self):
        if not self.config.get('enabled'):return {'enabled':False,'available':False}
        try:
            manifest=self.request('/api/v1/capabilities')
            return {'enabled':True,'available':True,'version':manifest.get('service',{}).get('version',manifest.get('service',{}).get('service_version')),'api_version':manifest.get('service',{}).get('api_version'),'manifest':manifest,'probe_available':any(c.get('kind')=='probe' or str(c.get('id','')).startswith(('probe.','link.probe.')) for c in manifest.get('capabilities',[]))}
        except ValueError as exc:return {'enabled':True,'available':False,'notice':str(exc)}
    def capabilities(self):
        from novel_version import VERSION
        health=self.status()
        return {'provider_id':'pucatch','adapter_version':VERSION,'reported_version':health.get('version'),
                'adapter_fingerprint':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'verification':'public_manifest_checked' if health.get('available') else 'adapter_code_only',
                'health':{k:v for k,v in health.items() if k!='manifest'},'manifest':health.get('manifest'),
                'execution_verified':False,'transport':'http_api_v1','auth':'public',
                'operations':['public_metadata_probe','article_capture','video_capture','audio_capture','owned_job_status','owned_job_cancel','bounded_article_read'],
                'limitations':['服务报告的sample_verified不是本工作台实际执行验收','文章API不支持强制预算；申报大小不是文章流量上限','未提供转写或任意工具执行；不自动启动服务或重试'],
                'traffic_policy':{'unknown_or_over_1GB':'manual_handoff','cumulative_limit_bytes':1_000_000_000,'budget_scope':'all_workspace_capture_jobs_including_uncertain'}}

    def list_jobs(self,project,task_id='',offset=0,limit=20):
        from research_workspace import ResearchWorkspace
        ResearchWorkspace(allow_novel=True).project(project)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=20:raise ValueError('调用记录分页无效')
        path=self.directory/'jobs.sqlite3';items=[]
        if path.is_file():
            db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
            try:
                for row in db.execute('SELECT * FROM jobs ORDER BY rowid DESC'):
                    request=json.loads(row['request'])
                    if request.get('project')==project and (not task_id or request.get('task',{}).get('task_id')==task_id):items.append({**dict(row),'request':request})
            finally:db.close()
        end=offset+min(limit,max(0,len(items)-offset))
        return {'project':project,'jobs':items[offset:end],'total':len(items),'next_offset':end if end<len(items) else None,'notice':'调用提交状态不是实时完成状态；不确定请求不重发，历史预算不自动退还'}

    def require_capability(self,capability):
        manifest=self.request('/api/v1/capabilities')
        matches=[c for c in manifest.get('capabilities',[]) if c.get('id')==capability]
        if len(matches)!=1:raise ValueError('PuCatch未声明能力: '+capability)
        levels=matches[0].get('levels',{})
        if levels.get('dependencies_available') is not True or levels.get('sample_verified')=='failed':raise ValueError('PuCatch能力依赖缺失或样例失败: '+capability)
    def probe(self,url,kind):
        self.enabled();public_url(url)
        if kind not in ('article','video','audio'):raise ValueError('只支持article/video/audio')
        self.require_capability('link.probe.'+kind)
        data=self.request('/api/v1/probe',{'url':url,'content_type':kind,'auth':'public'})
        return {'source_url':url,'kind':kind,'metadata':data,'saved':False,'canon':False,'notice':'公开解析不代表事实已核实；不创建采集任务'}
    @contextmanager
    def connection(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.directory/'jobs.sqlite3',timeout=10)
        db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS jobs(operation_key TEXT PRIMARY KEY, request TEXT NOT NULL, job_id TEXT, state TEXT NOT NULL)')
        try:
            with db:yield db
        finally:db.close()
    def start(self,url,kind,reason,operation_key,project='',task_ref=None,expected_bytes=None):
        self.enabled();public_url(url)
        if kind not in ('article','video','audio'):raise ValueError('只支持article/video/audio')
        if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:raise ValueError('请说明需要采集的研究缺口')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',operation_key):raise ValueError('operation_key格式无效')
        from research_traffic import proxy_state,check_size,LIMIT
        traffic=proxy_state()
        values={'url':url,'kind':kind,'reason':reason}
        if expected_bytes is not None:values['expected_bytes']=expected_bytes
        if project:
            from research_workspace import ResearchWorkspace
            workspace=ResearchWorkspace(allow_novel=True);workspace.project(project)
            values['project']=project
        if task_ref is not None:values['task_ref']=task_ref
        if bool(project)!=bool(task_ref):raise ValueError('通用采集必须同时提供项目和当前任务精确引用')

        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM jobs WHERE operation_key=?',(operation_key,)).fetchone()
            if old:
                previous=json.loads(old['request']);previous.pop('task',None);previous.pop('traffic',None)
                if previous!=values:raise ValueError('operation_key已用于不同采集请求')
                if old['job_id']:return {'job_id':old['job_id'],'reused':True,'state':old['state']}
                raise ValueError('先前请求结果不确定；请检查PuCatch任务，不自动重试以免重复采集')
            if project:
                if not isinstance(task_ref,dict) or set(task_ref)!={'session_id','revision','fingerprint'}:raise ValueError('task_ref须包含session_id/revision/fingerprint')
                selected=workspace.resume(project,task_ref['session_id']);snapshot=selected['session_backup']
                if not snapshot or type(task_ref['revision']) is not int or any(snapshot[k]!=task_ref[k] for k in task_ref) or not selected['automatic_development_allowed']:
                    raise ValueError('采集任务引用过时、不是当前active方向或指纹不符；请重新恢复研究任务')
                values['task']={**task_ref,'task_id':selected['task_id'],'direction_revision':selected['direction_revision'],'stage':selected['stage']}
            used=sum(json.loads(row['request']).get('expected_bytes',LIMIT) for row in db.execute('SELECT request FROM jobs'))
            check_size(expected_bytes,used)
            self.require_capability('task.create.'+kind)
            values['traffic']=traffic
            request=json.dumps(values,sort_keys=True,ensure_ascii=False)
            db.execute('INSERT INTO jobs VALUES(?,?,NULL,?)',(operation_key,request,'pending'))
        try:
            payload={'url':url,'content_type':kind,'auth':'public'}
            if kind!='article':payload['budget_bytes']=expected_bytes
            else:payload['include_images']=False
            data=self.request('/api/v1/tasks',payload,{'Idempotency-Key':'pk-'+hashlib.sha256((str(self.directory.resolve())+':'+operation_key).encode()).hexdigest()})
            job=data.get('task_id','')
            if not re.fullmatch(r'[a-f0-9]{12}',job):raise ValueError('采集服务未返回有效任务ID')
            with self.connection() as db:db.execute('UPDATE jobs SET job_id=?,state=? WHERE operation_key=?',(job,'submitted',operation_key))
            return {'job_id':job,'reused':False,'status':data.get('state'),'source_url':url,'reason':reason,'canon':False,'project':project,'task':values.get('task'),'traffic':traffic,'expected_bytes':expected_bytes,'size_verification':'caller_declared','budget_requested':expected_bytes if kind!='article' else None,'budget_enforced':data.get('budget',{}).get('enforced',False if kind=='article' else None),'notice':'文章API不支持实际流量预算，默认不抓图片；申报大小非传输上限' if kind=='article' else '媒体任务提交了服务端预算，实际用量须查询任务核对'}
        except Exception:
            with self.connection() as db:db.execute('UPDATE jobs SET state=? WHERE operation_key=?',('uncertain',operation_key))
            raise
    def owned(self,job_id,project=''):
        if not re.fullmatch(r'[a-f0-9]{12}',job_id):raise ValueError('任务ID无效')
        with self.connection() as db:row=db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
        if row is None:raise ValueError('只允许访问本工作台创建的采集任务')
        request=json.loads(row['request'])
        if project:
            from research_workspace import ResearchWorkspace
            ResearchWorkspace(allow_novel=True).project(project)
            if request.get('project')!=project:raise ValueError('采集任务不属于当前项目；旧无归属任务仅原完整档可读')
        return request
    def job(self,job_id,project=''):
        self.enabled();owned=self.owned(job_id,project)
        data=self.request('/api/v1/tasks/'+job_id)
        if data.get('task_id')!=job_id or data.get('source_url')!=owned['url'] or data.get('content_type')!=owned['kind']:raise ValueError('采集任务与原请求不一致')
        return data
    def cancel(self,job_id,project=''):
        self.enabled();self.owned(job_id,project)
        return self.request('/api/v1/tasks/'+job_id+'/cancel',{})
    def read_article(self,job_id,char_offset=0,max_chars=3000,expected_fingerprint='',project=''):
        self.enabled();owned=self.owned(job_id,project)
        if owned['kind']!='article':raise ValueError('媒体下载不等于文本；本版只读取已采集文章')
        if type(char_offset) is not int or type(max_chars) is not int or not 0<=char_offset<=2_000_000 or not 1<=max_chars<=6000:raise ValueError('读取范围无效，max_chars最多6000')
        job=self.job(job_id,project)
        if job.get('state')!='completed':raise ValueError('文章尚未确认完成')
        artifacts=self.request('/api/v1/tasks/'+job_id+'/artifacts').get('artifacts',[])
        candidates=[a for a in artifacts if a.get('type')=='article_markdown']
        if len(candidates)!=1:raise ValueError('文章产物缺失或多候选，不能自动选择')
        artifact=candidates[0];aid=artifact.get('artifact_id','');fp=artifact.get('sha256','')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}',aid) or not re.fullmatch('[a-f0-9]{64}',fp):raise ValueError('产物标识或指纹无效')
        if type(artifact.get('bytes')) is not int or not 0<=artifact['bytes']<=2*1024*1024:raise ValueError('文章大小未知或超过2MiB')
        if expected_fingerprint and expected_fingerprint!=fp:raise ValueError('采集文章已变化；重新核对来源')
        parts=[];offset=0
        for _ in range(64):
            segment=self.request('/api/v1/artifacts/'+aid+'/content?offset='+str(offset)+'&limit=65536')
            text=segment.get('content')
            if not isinstance(text,str) or segment.get('content_fingerprint')!='sha256:'+fp:raise ValueError('文章分段指纹不一致')
            parts.append(text)
            if sum(len(p.encode('utf-8')) for p in parts)>2*1024*1024:raise ValueError('文章超过2MiB')
            if segment.get('eof') is True:break
            next_offset=segment.get('next_offset')
            if type(next_offset) is not int or next_offset!=offset+len(text) or next_offset<=offset:raise ValueError('文章分页无进展')
            offset=next_offset
        else:raise ValueError('文章分段过多')
        text=''.join(parts);raw=text.encode('utf-8')
        if hashlib.sha256(raw).hexdigest()!=fp or len(raw)!=artifact['bytes']:raise ValueError('文章实际内容与产物指纹不符')
        if char_offset>len(text):raise ValueError('偏移超出文章范围')
        end=min(len(text),char_offset+max_chars)
        return {'source_url':owned['url'],'reason':owned['reason'],'artifact_id':aid,'fingerprint':fp,'fingerprint_scheme':'sha256_utf8_content',
                'body':text[char_offset:end],'line_start':text[:char_offset].count('\n')+1,'line_end':text[:end].count('\n')+1,
                'next_char_offset':end if end<len(text) else None,'saved_to_research':False,'verification':'content_hash_checked_not_fact_verified','canon':False}
