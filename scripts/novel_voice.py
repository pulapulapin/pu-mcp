"""Versioned voice trials and reported judgments; no synthesis or audio analysis."""
import json
import os
import hashlib
import stat
from pathlib import Path
from typing import Literal, Union
from pydantic import Field, model_validator
from novel_evidence import Model, encode
from novel_store import digest, identifier, now


class SourceRef(Model):
    source_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    revision: int = Field(ge=1)


class RecordRef(Model):
    record_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    revision: int = Field(ge=1)


class LicensePart(Model):
    license_name: str = Field(min_length=1, max_length=200)
    commercial_use: Literal['allowed', 'prohibited', 'unknown'] = 'unknown'
    evidence: list[SourceRef] = Field(default_factory=list, max_length=10)
    restrictions: str = Field(min_length=1, max_length=3000)
    checked_on: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')

    @model_validator(mode='after')
    def evidence_required(self):
        from datetime import date
        date.fromisoformat(self.checked_on)
        if self.commercial_use != 'unknown' and not self.evidence:
            raise ValueError('许可允许/禁止声明需保留依据；无证据请用unknown')
        return self


class License(Model):
    kind: Literal['license']
    model_id: str = Field(min_length=1, max_length=200)
    code_revision: str = Field(min_length=1, max_length=200)
    weights_revision: str = Field(min_length=1, max_length=200)
    code: LicensePart
    weights: LicensePart


class Trial(Model):
    kind: Literal['trial']
    model_id: str = Field(min_length=1, max_length=200)
    weights_revision: str = Field(min_length=1, max_length=200)
    license_record: RecordRef
    narration: SourceRef
    audio: SourceRef
    additional_audio: list[SourceRef] = Field(default_factory=list, max_length=10)
    generation_report: SourceRef | None = None
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    spoken_text: str = Field(default='', max_length=6000)
    duration_sec: float = Field(gt=0, le=86400, allow_inf_nan=False)
    duration_basis: str = Field(min_length=1, max_length=1000)
    intended_use: Literal['internal_test', 'commercial'] = 'internal_test'
    notes: str = Field(min_length=1, max_length=3000)

    @model_validator(mode='after')
    def parameters_bounded(self):
        if len(self.parameters)>50 or len(encode(self.parameters))>16000:
            raise ValueError('参数超限')
        for k,v in self.parameters.items():
            if isinstance(v,float) and not __import__('math').isfinite(v):
                raise ValueError('参数必须为有限数值')
            if len(k)>80 or any(x in k.lower() for x in ('api_key','password','authorization','access_token','secret')):
                raise ValueError('参数不能包含凭据')
            if isinstance(v,str) and len(v)>1000:
                raise ValueError('参数文本超长')
        return self


class Metric(Model):
    name: str = Field(min_length=1, max_length=100)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=50)


class Detection(Model):
    source_reports: list[SourceRef] = Field(default_factory=list, max_length=10)
    kind: Literal['detection']
    trial: RecordRef
    report: SourceRef
    analyzed_audio: SourceRef
    tool_name: str = Field(min_length=1, max_length=200)
    tool_version: str = Field(min_length=1, max_length=200)
    method: str = Field(min_length=1, max_length=2000)
    generated_at: str = Field(min_length=1, max_length=100)
    metrics: list[Metric] = Field(default_factory=list, max_length=100)
    transcript: str = Field(default='', max_length=12000)
    limitations: str = Field(min_length=1, max_length=3000)


class Listening(Model):
    kind: Literal['listening']
    trial: RecordRef
    listened_audio: SourceRef
    listener: str = Field(min_length=1, max_length=200)
    verdict: Literal['rejected', 'needs_revision', 'promising', 'undecided']
    feedback: str = Field(min_length=1, max_length=6000)
    evidence: list[SourceRef] = Field(min_length=1, max_length=10)


class OwnerDecision(Model):
    kind: Literal['owner_decision']
    trial: RecordRef
    decision: Literal['approved', 'rejected', 'deferred']
    quoted_instruction: str = Field(min_length=1, max_length=3000)
    scope: str = Field(min_length=1, max_length=1000)
    evidence: list[SourceRef] = Field(min_length=1, max_length=10)


class VoiceRecord(Model):
    record_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    payload: Union[License, Trial, Detection, Listening, OwnerDecision]


class DetectionReport(Model):
    source_reports: list[SourceRef] = Field(default_factory=list, max_length=10)
    schema_version: Literal[1]
    input_audio_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    input_narration_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    tool_name: str = Field(min_length=1, max_length=200)
    tool_version: str = Field(min_length=1, max_length=200)
    method: str = Field(min_length=1, max_length=2000)
    generated_at: str = Field(min_length=1, max_length=100)
    metrics: list[Metric] = Field(default_factory=list, max_length=100)
    transcript: str = Field(default='', max_length=12000)
    limitations: str = Field(min_length=1, max_length=3000)


def schema(db):
    db.execute('CREATE TABLE voice_record_versions(project TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL, kind TEXT NOT NULL, trial_id TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(project,id,revision))')


class Voice:
    def __init__(self,w):
        self.w=w;self.store=w.store;self.e=w.evidence

    def row(self,project,record_id,revision=0,db=None):
        self.w.project_id(project);identifier(record_id)
        if revision<0:raise ValueError('版本不能为负')
        if db is None:
            with self.store.connection() as con:return self.row(project,record_id,revision,con)
        r=db.execute('SELECT * FROM voice_record_versions WHERE project=? AND id=? AND (?=0 OR revision=?) ORDER BY revision DESC LIMIT 1',(project,record_id,revision,revision)).fetchone()
        if not r:raise ValueError('当前项目中不存在该试验记录版本')
        return {**dict(r),'body':json.loads(r['body'])}

    def source(self,project,ref,media=None,fresh=True):
        d=self.e.get(ref['source_id'],project,ref['revision'])
        if fresh and d['stale']:raise ValueError('引用的来源已变化；需重新核对版本')
        if media and d['source']['media_type'] not in media:raise ValueError('来源媒介与试验角色不符')
        return d['source']

    def license_state(self,project,p):
        states=[p['code']['commercial_use'],p['weights']['commercial_use']]
        refs=p['code']['evidence']+p['weights']['evidence']
        stale=any(self.e.get(r['source_id'],project,r['revision'])['stale'] for r in refs)
        if 'prohibited' in states:return 'blocked_prohibited'
        if 'unknown' in states or stale:return 'blocked_unknown_or_stale'
        if p['code_revision'].lower() in ('unknown','main','latest') or p['weights_revision'].lower() in ('unknown','main','latest'):
            return 'blocked_unpinned_version'
        return 'declared_compatible_requires_review'

    def trial(self,project,ref):
        r=self.row(project,ref['record_id'],ref['revision'])
        if r['kind']!='trial':raise ValueError('引用对象不是声音试验')
        return r['body']['payload']

    def validate(self,project,data):
        p=data['payload'];kind=p['kind'];self.w.project_id(project)
        if kind=='license':
            for part in (p['code'],p['weights']):
                for ref in part['evidence']:self.source(project,ref)
            return
        if kind=='trial':
            lic=self.row(project,p['license_record']['record_id'],p['license_record']['revision'])
            if lic['kind']!='license':raise ValueError('license_record必须是许可记录')
            lp=lic['body']['payload']
            if lp['model_id']!=p['model_id'] or lp['weights_revision']!=p['weights_revision']:
                raise ValueError('试验模型/权重版本与许可记录不一致')
            self.source(project,p['narration'],('text','article'))
            for r in [p['audio']]+p['additional_audio']:self.source(project,r,('audio',))
            if p['generation_report']:self.source(project,p['generation_report'],('text','article'))
            return
        t=self.trial(project,p['trial'])
        valid=[t['audio']]+t['additional_audio']
        if kind=='detection':
            report_data=self.load_report(project,p['report'])
            audio_data=self.source(project,p['analyzed_audio'],('audio',))
            narration_data=self.source(project,t['narration'],('text','article'))
            if report_data['input_audio_sha256']!=audio_data['fingerprint'] or report_data['input_narration_sha256']!=narration_data['fingerprint']:
                raise ValueError('报告输入指纹与试验音频/旁白不一致')
            if any(p[k]!=report_data[k] for k in ('tool_name','tool_version','method','generated_at','metrics','transcript','limitations','source_reports')):
                raise ValueError('检测内容须与已登记报告一致，不能把手填结果冒充导入')
            if p['analyzed_audio'] not in valid:raise ValueError('检测输入不是该试验保存的音频版本')
            self.source(project,p['analyzed_audio'],('audio',))
            self.source(project,p['report'],('text','article'))
            for ref in p['source_reports']:self.source(project,ref)
        elif kind=='listening':
            if p['listened_audio'] not in valid:raise ValueError('试听对象不是该试验音频')
            self.source(project,p['listened_audio'],('audio',),fresh=False)
            for r in p['evidence']:self.source(project,r,fresh=False)
        else:
            for r in p['evidence']:self.source(project,r,fresh=False)

    def preview(self,project,record):
        data=VoiceRecord.model_validate(record).model_dump(mode='json')
        self.validate(project,data)
        with self.store.connection() as db:
            old=db.execute('SELECT revision,body FROM voice_record_versions WHERE project=? AND id=? ORDER BY revision DESC LIMIT 1',(project,data['record_id'])).fetchone()
        if old and json.loads(old['body'])['payload']['kind']!=data['payload']['kind']:raise ValueError('已有记录不能更换判断类别')
        return {'project':project,'record':data,'baseline':old['revision'] if old else 0,'preview_fingerprint':digest(encode(data)),
                'diff':self.e.diff(json.loads(old['body']) if old else {},data),'saved':False,'canon':False,
                'notice':'许可结论、检测、听评与Owner决定为各自来源声明；不运行模型，不自动批准使用或Canon'}

    def save(self,project,record,baseline,preview_fingerprint,operation_key,_namespace=None,_request=None):
        data=VoiceRecord.model_validate(record).model_dump(mode='json');self.w.project_id(project)
        ns=_namespace or 'voice-record:'+project+':'+data['record_id'];req=_request or {'record':data,'baseline':baseline,'preview_fingerprint':preview_fingerprint}
        with self.store.connection() as db:
            retry=self.e.retry(db,ns,operation_key,req)
            if retry:return retry
        if preview_fingerprint!=digest(encode(data)):raise ValueError('记录与预览内容不一致')
        self.validate(project,data)
        p=data['payload'];trial_id=p['trial']['record_id'] if p['kind'] in ('detection','listening','owner_decision') else data['record_id'] if p['kind']=='trial' else ''
        with self.store.connection(write=True) as db:
            retry=self.e.retry(db,ns,operation_key,req)
            if retry:return retry
            self.validate(project,data)
            old=db.execute('SELECT revision,kind,body FROM voice_record_versions WHERE project=? AND id=? ORDER BY revision DESC LIMIT 1',(project,data['record_id'])).fetchone()
            current=old['revision'] if old else 0
            if baseline!=current:raise ValueError('声音记录版本冲突；重新预览')
            if old and old['kind']!=p['kind']:raise ValueError('已有记录不能更换类别')
            # Trial identity stays stable; revise parameters by creating a new trial/version.
            if old and p['kind'] in ('detection','listening','owner_decision') and json.loads(old['body'])['payload']['trial']!=p['trial']:
                raise ValueError('判断记录不得改绑另一试验或版本')
            unchanged=old and old['body']==encode(data);revision=current if unchanged else current+1
            if not unchanged:db.execute('INSERT INTO voice_record_versions VALUES(?,?,?,?,?,?,?)',(project,data['record_id'],revision,p['kind'],trial_id,encode(data),now()))
            result={'project':project,'record_id':data['record_id'],'revision':revision,'kind':p['kind'],'saved':True,'canon':False,'approval_verified':False}
            self.e.operation(db,ns,operation_key,req,result)
            return result

    def get(self,project,record_id,revision=0):
        row=self.row(project,record_id,revision);latest=self.row(project,record_id);p=row['body']['payload'];result={'project':project,'record_id':record_id,'revision':row['revision'],'latest_revision':latest['revision'],'historical':row['revision']!=latest['revision'],'record':row['body'],'created_at':row['created'],'canon':False,'approval_verified':False}
        if p['kind']=='license':result['commercial_precheck']=self.license_state(project,p)
        elif p['kind']=='trial':
            lic=self.row(project,p['license_record']['record_id'],p['license_record']['revision'])
            result['commercial_precheck']=self.license_state(project,lic['body']['payload'])
            result['license_record']=self.get(project,p['license_record']['record_id'],p['license_record']['revision'])
            if result['license_record']['historical']:
                result['commercial_precheck']='blocked_superseded_license'
            result['spoken_text_fingerprint']=digest(p['spoken_text']) if p['spoken_text'] else None
            result['spoken_text_fingerprint_scheme']='sha256_utf8_decoded_text'
            result['artifacts']=[{'role':role,**self.e.get(r['source_id'],project,r['revision'])} for role,r in [('narration',p['narration']),('audition_audio',p['audio'])]+[('additional_audio',x) for x in p['additional_audio']]]
            with self.store.connection() as db:
                related=db.execute('SELECT id,revision,kind,body FROM voice_record_versions v WHERE project=? AND trial_id=? AND kind<>? AND revision=(SELECT max(revision) FROM voice_record_versions x WHERE x.project=v.project AND x.id=v.id) ORDER BY id',(project,record_id,'trial')).fetchall()
                rejected=db.execute('SELECT id,revision,body FROM voice_record_versions WHERE project=? AND trial_id=? AND kind=? ORDER BY id,revision',(project,record_id,'listening')).fetchall()
            result['rejection_history']=[{'record_id':r['id'],'revision':r['revision'],'payload':json.loads(r['body'])['payload']} for r in rejected if json.loads(r['body'])['payload']['verdict']=='rejected']
            # A judgment is only applicable to the exact trial version it references.
            result['listening_status']='reported' if any(r['kind']=='listening' for r in related) else 'no_listening_record'
            result['owner_decision_status']='reported' if any(r['kind']=='owner_decision' for r in related) else 'no_owner_decision'
            result['judgments']=[{'record_id':r['id'],'revision':r['revision'],'kind':r['kind'],'origin':{'detection':'imported_automatic_result','listening':'reported_human_listening','owner_decision':'reported_owner_decision'}[r['kind']],'applies_to_this_version':json.loads(r['body'])['payload']['trial']['revision']==row['revision'],'approval_verified':False,'payload':json.loads(r['body'])['payload']} for r in related]
        else:result['judgment_origin']={'detection':'imported_automatic_result','listening':'reported_human_listening','owner_decision':'reported_owner_decision'}[p['kind']]
        return result

    def list(self,project,kind='',trial_id='',offset=0,limit=20):
        self.w.project_id(project)
        if kind and kind not in ('license','trial','detection','listening','owner_decision'):raise ValueError('声音记录类别无效')
        if offset<0 or not 1<=limit<=50:raise ValueError('分页范围无效')
        with self.store.connection() as db:
            rows=db.execute('SELECT id,revision,kind,trial_id FROM voice_record_versions v WHERE project=? AND (?="" OR kind=?) AND (?="" OR trial_id=?) AND revision=(SELECT max(revision) FROM voice_record_versions x WHERE x.project=v.project AND x.id=v.id) ORDER BY id',(project,kind,kind,trial_id,trial_id)).fetchall()
        return {'project':project,'records':[dict(r) for r in rows[offset:offset+limit]],'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None}

    def load_report(self,project,report):
        source=self.source(project,report,('text',))
        if source['binding']['kind']!='local_file' or Path(source['locator']).suffix.lower()!='.json':
            raise ValueError('检测导入需已登记本地JSON报告，不访问任意路径')
        fd=os.open(source['locator'],os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
        with os.fdopen(fd,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('报告须为普通文件')
            raw=stream.read(262145)
        if len(raw)>262144:raise ValueError('检测JSON超过256KiB；请提供有限摘要报告')
        if hashlib.sha256(raw).hexdigest()!=source['fingerprint']:raise ValueError('检测报告在导入期间变化')
        return DetectionReport.model_validate_json(raw).model_dump(mode='json')

    def import_detection(self,project,record_id,trial,report,analyzed_audio,baseline=0,operation_key='',preview_only=True):
        # Retry must return its original result even if an external report later changes.
        request={'trial':trial,'report':report,'analyzed_audio':analyzed_audio,'baseline':baseline}
        namespace='voice-import:'+project+':'+record_id
        if not preview_only:
            with self.store.connection() as db:
                retry=self.e.retry(db,namespace,operation_key,request)
                if retry:return retry
        self.w.project_id(project)
        t=self.trial(project,trial);d=self.load_report(project,report)
        audio=self.source(project,analyzed_audio,('audio',));narration=self.source(project,t['narration'],('text','article'))
        if d['input_audio_sha256']!=audio['fingerprint'] or d['input_narration_sha256']!=narration['fingerprint']:
            raise ValueError('报告输入指纹与关联的音频/旁白版本不一致')
        payload={k:d[k] for k in ('tool_name','tool_version','method','generated_at','metrics','transcript','limitations','source_reports')}
        record={'record_id':record_id,'payload':{'kind':'detection','trial':trial,'report':report,'analyzed_audio':analyzed_audio,**payload}}
        p=self.preview(project,record)
        if preview_only:return {**p,'import_status':'report_bytes_and_input_fingerprints_checked','analysis_reexecuted':False}
        if p['baseline']!=baseline:raise ValueError('导入记录版本冲突')
        return self.save(project,record,baseline,p['preview_fingerprint'],operation_key,
                         _namespace=namespace,_request=request)
