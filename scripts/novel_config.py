"""Portable local paths. JSON configuration never contains credentials."""
import json
import re
import os
from pathlib import Path
from extension_registry import AVAILABLE as MODULE_NAMES

ROOT = Path(__file__).resolve().parent.parent
SOURCE_CHECKOUT = (ROOT / 'novels/projects').is_dir()
HOME_DATA = Path.home() / '.local/share/novel-workbench'
PUBLIC_HOME = Path.home() / '.local/share/pu-knowledge'

def load_settings(neutral=False):
    old_config=os.environ.get('NOVEL_WORKBENCH_CONFIG','')
    public_config=os.environ.get('PUKNOWLEDGE_CONFIG','')
    if old_config and public_config and Path(old_config).expanduser().resolve()!=Path(public_config).expanduser().resolve():raise ValueError('新旧配置环境变量冲突，请只指定同一文件')
    explicit = public_config or old_config
    local = ROOT / '.local/novel-workbench/config.json'
    public_local = ROOT / '.local/pu-knowledge/config.json'
    if explicit:
        file = Path(explicit).expanduser().resolve()
    elif SOURCE_CHECKOUT and local.is_file():
        file = local
    elif SOURCE_CHECKOUT and public_local.is_file():
        file = public_local
    else:
        file = local
    raw = {}
    if explicit or (SOURCE_CHECKOUT and file.is_file()):
        raw = json.loads(file.read_text(encoding='utf-8'))
        allowed = {'data_dir', 'projects_dir', 'projects', 'project_stores', 'books_root', 'collections', 'pucatch', 'capture', 'research_roots', 'game_repositories', 'project_states', 'research_projects', 'workspaces', 'fs_workspaces', 'modules', 'writing_contexts'}
        if not isinstance(raw, dict) or set(raw) - allowed:
            raise ValueError('配置必须是JSON对象，仅允许data_dir/projects_dir/projects/project_stores/books_root/collections/pucatch/capture/research_roots/game_repositories/project_states/research_projects/workspaces/fs_workspaces/modules')
    if 'workspaces' in raw:
        if 'research_projects' in raw and raw['workspaces']!=raw['research_projects']:raise ValueError('workspaces与research_projects配置冲突')
        raw['research_projects']=raw['workspaces']
    if 'capture' in raw:
        if 'pucatch' in raw and raw['capture']!=raw['pucatch']:raise ValueError('capture与pucatch配置冲突')
        raw['pucatch']=raw['capture']
    base = file.parent
    def path(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('配置目录必须是非空字符串')
        p = Path(value).expanduser()
        return (p if p.is_absolute() else base / p).resolve()
    default_projects = ROOT / 'novels/projects' if SOURCE_CHECKOUT else PUBLIC_HOME / 'projects'
    default_data = (ROOT / '.local/novel-workbench' if (ROOT / '.local/novel-workbench').is_dir() else ROOT / '.local/pu-knowledge') if SOURCE_CHECKOUT else PUBLIC_HOME / 'data'
    projects = path(raw['projects_dir']) if 'projects_dir' in raw else default_projects.resolve()
    data = path(os.environ['NOVEL_WORKBENCH_DATA']) if os.environ.get('NOVEL_WORKBENCH_DATA') else path(raw['data_dir']) if 'data_dir' in raw else default_data.resolve()
    books = path(raw['books_root']) if 'books_root' in raw else (PUBLIC_HOME / 'books').resolve()
    registered = raw.get('projects', {})
    if not isinstance(registered, dict):
        raise ValueError('projects必须是项目ID到目录的JSON对象')
    for key in registered:
        if not isinstance(key, str) or not key or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in key):
            raise ValueError('项目ID只能使用小写字母、数字、短横线和下划线')
    registered = {key: path(value) for key, value in registered.items()}
    stores_raw = raw.get('project_stores', {})
    if not isinstance(stores_raw, dict):
        raise ValueError('project_stores必须是项目ID到存储配置的JSON对象')
    project_stores = {}
    for key, value in stores_raw.items():
        if key not in registered:
            raise ValueError('project_stores只能绑定显式projects项目: ' + str(key))
        if not isinstance(value, dict) or set(value) != {'path', 'mode'}:
            raise ValueError('project_stores条目必须且只能包含path/mode')
        if value['mode'] not in ('shadow', 'active'):
            raise ValueError('project_stores.mode必须是shadow或active')
        store_path = path(value['path'])
        configured = registered[key]
        project_root = configured.parent if configured.name == '_storylab' else configured
        expected = (project_root / '.puknowledge').resolve()
        if store_path != expected:
            raise ValueError('项目数据库必须位于项目根目录.puknowledge: ' + key)
        project_stores[key] = {'path': store_path, 'mode': value['mode']}
    # Non-neutral legacy installs may still ship dnd collections; neutral/public configs do not infer them.
    supplied = raw.get('collections', {})
    if not supplied and not neutral and 'workspaces' not in raw and 'research_projects' not in raw:
        dnd_root = registered.get('dnd', projects / 'dnd')
        if (dnd_root / 'source').is_dir():
            supplied = {'dnd-handoff': str(dnd_root / 'source')}
    if not isinstance(supplied, dict):
        raise ValueError('collections必须是集合ID到目录的JSON对象')
    for key in supplied:
        if not isinstance(key, str) or not key or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in key):
            raise ValueError('资料集合ID只能使用小写字母、数字、短横线和下划线')
    capture=raw.get('pucatch', {})
    if not isinstance(capture,dict) or set(capture)-{'enabled','base_url','repo','python','download_root'}:
        raise ValueError('capture/pucatch配置字段无效')
    if not isinstance(capture.get('enabled',False),bool):raise ValueError('capture.enabled必须是布尔值')
    configured={'enabled':capture.get('enabled',False)}
    if configured['enabled']:
        from urllib.parse import urlsplit
        url=capture.get('base_url','http://127.0.0.1:8787')
        parts=urlsplit(url)
        if parts.scheme!='http' or parts.hostname!='127.0.0.1' or not parts.port or parts.path not in ('','/') or parts.query or parts.fragment or parts.username or parts.password:
            raise ValueError('可选采集扩展仅允许http://127.0.0.1:端口本机服务')
        configured.update({'base_url':url.rstrip('/')})
        for key in ('repo','download_root','python'):
            if capture.get(key):configured[key]=capture[key]
    modules_raw=raw.get('modules',[])
    if modules_raw in ('',None):modules_raw=[]
    if isinstance(modules_raw,str):modules_raw=[p.strip() for p in modules_raw.split(',') if p.strip()]
    if not isinstance(modules_raw,list) or any(not isinstance(x,str) or x not in MODULE_NAMES for x in modules_raw):
        raise ValueError('modules须为已知模块名列表: '+','.join(MODULE_NAMES))
    research_projects=raw.get('research_projects',{})
    if not isinstance(research_projects,dict):raise ValueError('research_projects须为显式项目对象')
    fiction_ids=set(registered)
    if projects.is_dir():fiction_ids.update(p.name for p in projects.iterdir() if (p/'story-contract.json').is_file())
    research={}
    for key,value in research_projects.items():
        if not isinstance(key,str) or not re.fullmatch(r'[a-z0-9_-]{1,80}',key) or key in fiction_ids:raise ValueError('研究项目ID无效或与小说项目冲突')
        if not isinstance(value,dict) or not {'path','label','domain'}<=set(value) or set(value)-{'path','label','domain','fs_read'}:
            raise ValueError('研究项目须包含path/label/domain，可选fs_read')
        if any(not isinstance(value[k],str) or not value[k].strip() or len(value[k])>200 for k in ('label','domain')):raise ValueError('研究项目名称或业务域无效')
        entry={'path':path(value['path']),'label':value['label'].strip(),'domain':value['domain'].strip()}
        if 'fs_read' in value:entry['fs_read']=value['fs_read']
        research[key]=entry
    roots = raw.get('research_roots', [])
    if not isinstance(roots, list):
        raise ValueError('research_roots必须是许可目录列表')
    evidence_roots = [path(value) for value in roots]
    evidence_roots += [books] + [path(value) for value in supplied.values()]
    from novel_game import validate_repositories
    from workspace_fs import collect_fs_workspaces
    games = validate_repositories(raw.get('game_repositories', {}), path)
    states = raw.get('project_states', {})
    if not isinstance(states, dict) or any(not isinstance(k,str) or not re.fullmatch(r'[a-z0-9_-]{1,80}',k) or v not in ('active','paused') for k,v in states.items()):
        raise ValueError('project_states必须是项目ID到active/paused的对象')
    fs_workspaces=collect_fs_workspaces(research,raw.get('fs_workspaces'),path)
    from writing_context import validate_bindings
    writing_contexts=validate_bindings(raw.get('writing_contexts', {}), fiction_ids)
    return {'writing_contexts':writing_contexts, 'research_projects':research, 'game_repositories':games, 'project_states':states, 'research_roots': evidence_roots, 'pucatch':configured, 'capture':configured, 'modules':list(modules_raw), 'data_dir': data, 'projects_dir': projects, 'projects': registered, 'project_stores': project_stores, 'books_root': books,
            'collections': {key: path(value) for key, value in supplied.items()},'fs_workspaces':fs_workspaces}


def project_dirs(settings=None):
    """All novel projects: subfolders of projects_dir plus explicitly registered ones.

    Registered entries (config key "projects") let each novel keep its files in its own
    folder or repository; they override a same-named projects_dir child. Symlinks inside
    projects_dir are still ignored.
    """
    settings = settings or load_settings()
    found = {}
    root = settings['projects_dir']
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if child.is_dir() and not child.is_symlink() and (child / 'story-contract.json').is_file():
                found[child.name] = child
    for key, value in settings.get('projects', {}).items():
        found[key] = value
    return dict(sorted(found.items()))
