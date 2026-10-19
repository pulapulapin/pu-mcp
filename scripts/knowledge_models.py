"""Bounded declarative structures. Formulas are stored as text, never evaluated."""
from typing import Literal,Any
from pydantic import BaseModel,ConfigDict,Field,model_validator
from novel_evidence import Position
ID=r'^[a-zA-Z0-9_-]{1,80}$'
SHA=r'^[a-f0-9]{64}$'
class Model(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
class Dataset(Model):
 title:str=Field(min_length=1,max_length=200)
 scope:Literal['global','project']='project'
 purpose:Literal['reference','model','state']='reference'
class Column(Model):
 type:Literal['string','integer','number','boolean']
 required:bool=False
 unit:str=Field(default='',max_length=80)
 minimum:float|int|None=None
 maximum:float|int|None=None
 enum:list[str|int|float|bool]|None=Field(default=None,max_length=100)
class Structure(Model):
 fields:dict[str,Column]
 allowed_relations:list[str]=Field(default_factory=list,max_length=30)
 @model_validator(mode='after')
 def bounds(self):
  import re
  if not 1<=len(self.fields)<=80 or any(not re.fullmatch(ID,k) for k in self.fields):raise ValueError('结构须1–80个有名字段')
  if any(not re.fullmatch(ID,k) for k in self.allowed_relations):raise ValueError('关系类型无效')
  for c in self.fields.values():
   import math
   if c.type not in ('integer','number') and (c.minimum is not None or c.maximum is not None):raise ValueError('仅数值字段可定义数值边界')
   if any(value is not None and not math.isfinite(value) for value in (c.minimum,c.maximum)):raise ValueError('结构边界必须有限')
   if c.enum is not None:
    allowed={'string':(str,),'integer':(int,),'number':(int,float),'boolean':(bool,)}[c.type]
    if not c.enum or any(type(v) not in allowed or type(v) in (float,int) and not math.isfinite(v) for v in c.enum):raise ValueError('枚举类型须匹配字段且值有限')
   if c.minimum is not None and c.maximum is not None and c.minimum>c.maximum:raise ValueError('数值边界顺序无效')
  return self
class Binding(Model):
 source_id:str=Field(pattern=ID)
 source_revision:int=Field(ge=1)
 source_version_fingerprint:str=Field(pattern=SHA)
 field:str=Field(default='*',max_length=80)
 position:Position
class Record(Model):
 record_type:str=Field(pattern=ID)
 schema_revision:int=Field(ge=1)
 values:dict[str,Any]
 status:Literal['candidate','confirmed','withdrawn']='candidate'
 evidence:list[Binding]=Field(default_factory=list,max_length=30)
 execution:Literal['not_executed']='not_executed'
class Endpoint(Model):
 dataset_id:str=Field(pattern=ID)
 record_id:str=Field(pattern=ID)
 revision:int=Field(ge=1)
 fingerprint:str=Field(pattern=SHA)
class Relation(Model):
 relation_type:str=Field(pattern=ID)
 source:Endpoint=Field(alias='from')
 target:Endpoint=Field(alias='to')
 status:Literal['candidate','confirmed','withdrawn']='candidate'
MODELS={'dataset':Dataset,'schema':Structure,'record':Record,'relation':Relation}

def schema(db):
 db.execute('''CREATE TABLE knowledge_versions(kind TEXT NOT NULL,dataset_id TEXT NOT NULL,object_id TEXT NOT NULL,
 revision INTEGER NOT NULL,commit_revision INTEGER NOT NULL,body TEXT NOT NULL,fingerprint TEXT NOT NULL,created TEXT NOT NULL,provenance TEXT NOT NULL,
 PRIMARY KEY(kind,dataset_id,object_id,revision))''')
 db.execute('CREATE INDEX knowledge_snapshot ON knowledge_versions(dataset_id,commit_revision)')

def validate_values(structure,values):
 if set(values)-set(structure['fields']):raise ValueError('记录包含结构未定义字段')
 for name,spec in structure['fields'].items():
  if name not in values:
   if spec['required']:raise ValueError('缺少必填字段: '+name)
   continue
  value=values[name];kind=spec['type'];ok={'string':type(value) is str,'integer':type(value) is int,'number':type(value) in (int,float),'boolean':type(value) is bool}[kind]
  if not ok:raise ValueError('字段类型不匹配: '+name)
  if type(value) is str and len(value)>10000:raise ValueError('字段文本超过10000字符')
  if type(value) in (float,int):
   import math
   if not math.isfinite(value):raise ValueError('数值必须有限')
   if spec['minimum'] is not None and value<spec['minimum'] or spec['maximum'] is not None and value>spec['maximum']:raise ValueError('字段数值越界: '+name)
  if spec['enum'] is not None and not any(type(value) is type(v) and value==v for v in spec['enum']):raise ValueError('字段不在枚举中: '+name)
