"""One application API shared by MCP and local HTTP transports."""
from knowledge_data import Knowledge
from research_workspace import ResearchWorkspace

def workspace(project=''):
 # Knowledge may explicitly address registered story projects, without invoking
 # the novel resume algorithm or changing public research-session defaults.
 w=ResearchWorkspace(profile='workspace',store_project=project)
 from novel_config import project_dirs
 w.allowed.update({key:{'path':value,'label':key,'domain':'story'} for key,value in project_dirs(w.settings).items()})
 return w

def validate_params(args):
 string_keys={'project','kind','dataset_id','object_id','record_type','record_id','expected_fingerprint','preview_fingerprint','operation_key','direction','format','content','path','expected_sha256','prompt_id','customization_dataset_id','turn_instruction'}
 int_keys={'revision','dataset_revision','baseline','offset','limit','schema_revision','customization_revision'}
 bool_keys={'owner_confirmed','include_withdrawn'}
 for key,value in args.items():
  if key in string_keys and not isinstance(value,str):raise ValueError('参数须字符串: '+key)
  if key in int_keys and (type(value) is not int or value<0):raise ValueError('参数须非负整数: '+key)
  if key in bool_keys and type(value) is not bool:raise ValueError('参数须布尔值: '+key)
  if key=='filters' and value is not None and not isinstance(value,list):raise ValueError('filters须数组')
  if key=='evidence' and value is not None and not isinstance(value,list):raise ValueError('evidence须数组')
  if key=='field_mapping' and value is not None and not isinstance(value,dict):raise ValueError('field_mapping须对象')
  if key=='body' and not isinstance(value,dict):raise ValueError('body须对象')
  if key in ('base_ref','proposed_customization') and value is not None and not isinstance(value,dict):raise ValueError(key+'须对象')
OBJECTS={'dataset','schema','record','relation'}
DIRECT={'record_query':'query','relation_query':'relations','dataset_validate':'validate','import_preview':'import_preview','import_commit':'import_commit'}
def execute(workspace,operation,params):
 validate_params(params)
 k=Knowledge(workspace);args=dict(params)
 if operation=='prompt_resolve':
  from prompt_library import resolve
  return resolve(k,**args)
 if operation in DIRECT:return k.dispatch(DIRECT[operation],args)
 try:kind,action=operation.split('_',1)
 except ValueError:raise ValueError('未知知识API') from None
 if kind not in OBJECTS or action not in ('preview','save','get') or kind=='relation' and action=='get':raise ValueError('未知知识API')
 if kind=='dataset':
  if action=='get' and not args.get('dataset_id'):
   return k.datasets(**args)
  args['object_id']=args.get('dataset_id')
 args['kind']=kind
 return k.dispatch(action,args)
