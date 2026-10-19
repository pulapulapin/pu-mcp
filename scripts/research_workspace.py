"""Business-neutral research workspace over the existing evidence/version store."""
from pathlib import Path
from novel_config import load_settings,project_dirs
from novel_store import Store,identifier,SCHEMA
from novel_books import Books
from novel_evidence import Evidence
from novel_conversation import Conversations
from novel_version import VERSION
from research_resume import resume_task

class ResearchWorkspace:
    def __init__(self,allow_novel=False,profile=None):
        self.profile=profile or ('full' if allow_novel else 'research')
        self.settings=load_settings(neutral=profile=='workspace');self.allowed=dict(self.settings['research_projects'])
        if allow_novel:
            root=self.settings['projects_dir']
            if root.is_dir():
                for child in root.iterdir():
                    if child.is_dir() and not child.is_symlink() and child.resolve().is_relative_to(root):
                        try:identifier(child.name)
                        except ValueError:continue
                        self.allowed.setdefault(child.name,{'path':child.resolve(),'label':child.name,'domain':'legacy-workspace'})
            self.allowed.update({k:{'path':v,'label':k,'domain':'story'} for k,v in project_dirs(self.settings).items()})
        # The neutral workspace portal is the common discovery surface for all
        # configured projects.  Keep task recovery scoped to ``self.allowed``
        # (research projects), while advertising longform projects so callers
        # can choose writing_resume/writing_* for them.
        self.catalog=dict(self.allowed)
        if self.profile=='workspace':
            for key,path in project_dirs(self.settings).items():
                self.catalog.setdefault(key,{'path':path,'label':key,'domain':'longform'})
        self.store=Store(self.settings['data_dir']);self.research_roots=self.settings['research_roots']
        self.books=Books(self.store,self.settings['books_root']);self.evidence=Evidence(self);self.conversations=Conversations(self)
    def project(self,project):
        identifier(project)
        if project not in self.allowed:raise ValueError('项目不在本研究档显式登记范围内')
        path=Path(self.allowed[project]['path'])
        if not path.is_dir():raise ValueError('研究项目目录不存在，不自动创建业务资料')
        return path
    def project_id(self,project):self.project(project);return project
    def projects_list(self):
        projects=[]
        for key,value in sorted(self.catalog.items()):
            domain=value['domain']
            projects.append({'id':key,'label':value['label'],'domain':domain,
                             'available':Path(value['path']).is_dir(),
                             'workspace_interface':'writing' if domain=='longform' else 'task'})
        return {'projects':projects,'notice':'统一发现研究与长文项目；研究用task_*，长文用writing_*；global来源可复用，私有标注和任务不共享'}
    def resume(self,project,session_id=''):
        self.project(project);return resume_task(self,project,session_id)
    def status(self):
        return {'service':'PuKnowledge','version':VERSION,'storage_schema':SCHEMA,'profile':self.profile,'projects':self.projects_list()['projects'],
                'capabilities':['versioned_sources','project_annotations','task_direction_resume','optional_capture','tool_capability_catalog'],
                'limitations':['不从长文设定推断研究任务','未登记任务返回unassigned','不自动下载未知或大文件','没有语义搜索、自动转写或通用工具执行器']}
