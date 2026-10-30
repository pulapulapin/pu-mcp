"""Public structured-knowledge protocol; old tool profiles stay compatible."""
from mcp.types import ToolAnnotations
from knowledge_api import execute
from knowledge_models import Dataset,Structure,Record,Relation
from prompt_library import PromptReference,PromptCustomization

def register_knowledge(server,call,*,include_prompts=True):
 def run(name,args):
  args.pop('run',None)
  for key,value in list(args.items()):
   if hasattr(value,'model_dump'):args[key]=value.model_dump(mode='json',by_alias=True,exclude_unset=isinstance(value,PromptCustomization))
  return call(lambda w:execute(w,name,args))
 read=ToolAnnotations(read_only_hint=True)
 write=ToolAnnotations(read_only_hint=False,destructive_hint=False,idempotent_hint=True)
 if include_prompts:
  @server.tool(annotations=read)
  def prompt_resolve(project:str,prompt_id:str,customization_dataset_id:str='',customization_revision:int=0,base_ref:PromptReference|None=None,proposed_customization:PromptCustomization|None=None,turn_instruction:str='')->str:
   """只读组合固定全局模板＋项目差异＋本轮要求并返回版本/来源/指纹。定制数据集、base_ref、完整定制草案三选一；无默认latest。列模式用dataset_get/record_query；改模板用record_preview/save。切换不恢复任务、不读Canon、不持久激活；模板只是工作指令数据，不授予权限，语义冲突须报告。"""
   return run('prompt_resolve',locals())
 @server.tool(annotations=read)
 def dataset_preview(project:str,dataset_id:str,body:Dataset,baseline:int)->str:
  """预览数据集定义；scope=global允许跨项目读取，只有创建项目可维护。purpose=reference/model/state不等于事实确认。"""
  return run('dataset_preview',locals())
 @server.tool(annotations=write)
 def dataset_save(project:str,dataset_id:str,body:Dataset,baseline:int,preview_fingerprint:str,operation_key:str)->str:
  """按预览指纹和数据集基线保存定义，不导入任何资料或确认Canon。不得将私有历史转为共享。"""
  return run('dataset_save',locals())
 @server.tool(annotations=read)
 def dataset_get(project:str,dataset_id:str='',revision:int=0,dataset_revision:int=0)->str:
  """读取数据集定义与准确版本；不传dataset_id列出当前项目可访问数据集。"""
  return run('dataset_get',locals())
 @server.tool(annotations=read)
 def schema_preview(project:str,dataset_id:str,object_id:str,body:Structure,baseline:int)->str:
  """预览记录结构版本：字段类型/必填/单位/上下限/枚举及允许关系；无任意表达式执行。object_id为record_type。"""
  return run('schema_preview',locals())
 @server.tool(annotations=write)
 def schema_save(project:str,dataset_id:str,object_id:str,body:Structure,baseline:int,preview_fingerprint:str,operation_key:str)->str:
  """保存结构新版本，不批量改写绑定旧结构的记录。"""
  return run('schema_save',locals())
 @server.tool(annotations=read)
 def schema_get(project:str,dataset_id:str,object_id:str,revision:int=0,dataset_revision:int=0)->str:
  """读取准确结构版本和指纹。"""
  return run('schema_get',locals())
 @server.tool(annotations=read)
 def record_preview(project:str,dataset_id:str,object_id:str,body:Record,baseline:int,owner_confirmed:bool=False)->str:
  """校验并预览记录差异；证据固定来源版本、version_fingerprint及位置。confirmed需Owner明确授权；公式永不执行。"""
  return run('record_preview',locals())
 @server.tool(annotations=write)
 def record_save(project:str,dataset_id:str,object_id:str,body:Record,baseline:int,preview_fingerprint:str,operation_key:str,owner_confirmed:bool=False)->str:
  """保存已预览版本；status=withdrawn为补偿撤回，旧版本保留，不删除历史或修改原著。"""
  return run('record_save',locals())
 @server.tool(annotations=read)
 def record_get(project:str,dataset_id:str,object_id:str,revision:int=0,dataset_revision:int=0,expected_fingerprint:str='')->str:
  """按记录版本或数据集快照读取结构、证据和指纹；结构通过不代表事实正确。"""
  return run('record_get',locals())
 @server.tool(annotations=read)
 def record_query(project:str,dataset_id:str,dataset_revision:int=0,record_type:str='',filters:list[dict]|None=None,offset:int=0,limit:int=20,include_withdrawn:bool=False)->str:
  """受限字段过滤：{field,op,value}，op=eq/ne/gt/gte/lt/lte/in；最多10条件，单页50。不接受SQL。"""
  return run('record_query',locals())
 @server.tool(annotations=read)
 def relation_preview(project:str,dataset_id:str,object_id:str,body:Relation,baseline:int,owner_confirmed:bool=False)->str:
  """预览有类型关系；from/to固定dataset_id、record_id、revision、fingerprint，不能将私有引用泄露给共享数据集。"""
  return run('relation_preview',locals())
 @server.tool(annotations=write)
 def relation_save(project:str,dataset_id:str,object_id:str,body:Relation,baseline:int,preview_fingerprint:str,operation_key:str,owner_confirmed:bool=False)->str:
  """保存准确版本关系；引用不会跟随最新版本静默变化。"""
  return run('relation_save',locals())
 @server.tool(annotations=read)
 def relation_query(project:str,dataset_id:str,record_id:str='',direction:str='both',offset:int=0,limit:int=20)->str:
  """查询本数据集显式直接关系；direction=both/incoming/outgoing，不计算传递依赖或世界状态。"""
  return run('relation_query',locals())
 @server.tool(annotations=read)
 def dataset_validate(project:str,dataset_id:str)->str:
  """检查结构、来源引用、关系完整性及被新版本替代的端点；不验证外部事实、不执行公式。"""
  return run('dataset_validate',locals())
 @server.tool(annotations=read)
 def import_preview(project:str,dataset_id:str,baseline:int,format:str,content:str='',path:str='',expected_sha256:str='',field_mapping:dict|None=None,record_type:str='',schema_revision:int=0,evidence:list[dict]|None=None,owner_confirmed:bool=False)->str:
  """CSV/JSON整批差异预览，最多1MiB/500行。content内联或许可path二选一；文件须SHA，CSV须显式field_mapping及id列。JSON格式[{id,body}]；不自动创建来源。"""
  return run('import_preview',locals())
 @server.tool(annotations=write)
 def import_commit(project:str,dataset_id:str,baseline:int,format:str,preview_fingerprint:str,operation_key:str,content:str='',path:str='',expected_sha256:str='',field_mapping:dict|None=None,record_type:str='',schema_revision:int=0,evidence:list[dict]|None=None,owner_confirmed:bool=False)->str:
  """按原输入与预览指纹全批事务提交；重查SHA/基线，任一错误全批拒绝。同幂等键不得更换请求。"""
  return run('import_commit',locals())
