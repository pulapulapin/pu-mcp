import asyncio,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from novel_config import load_settings
from novel_workbench import Workbench
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

class ResearchWorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  for name in ['market','tools']:(self.root/name).mkdir()
  fiction=self.root/'fiction'/'story';fiction.mkdir(parents=True);(fiction/'story-contract.json').write_text('{}')
  self.cfg=self.root/'config.json';self.config={'data_dir':str(self.root/'data'),'projects_dir':str(self.root/'fiction'),'research_roots':[str(self.root)],'research_projects':{name:{'path':str(self.root/name),'label':name,'domain':'product-research'} for name in ['market','tools']}}
  self.cfg.write_text(json.dumps(self.config));env=patch.dict(os.environ,{'NOVEL_WORKBENCH_CONFIG':str(self.cfg),'NOVEL_WORKBENCH_DATA':str(self.root/'data')});env.start();self.addCleanup(env.stop)
 def workspace(self):
  from research_workspace import ResearchWorkspace
  return ResearchWorkspace()
 def test_nonfiction_project_needs_no_story_files_and_does_not_leak_into_novel(self):
  w=self.workspace();self.assertEqual(w.project('market'),self.root/'market')
  self.assertEqual(w.resume('market')['resume_mode'],'unassigned');self.assertFalse(w.resume('market')['automatic_development_allowed'])
  with self.assertRaises(ValueError):w.project('story')
  with self.assertRaises(ValueError):Workbench().resume('market')
  self.assertEqual(w.projects_list()['projects'][0]['domain'],'product-research')
 def test_workspace_catalog_lists_longform_without_widening_research_task_scope(self):
  from research_workspace import ResearchWorkspace
  w=ResearchWorkspace(profile='workspace');rows={x['id']:x for x in w.projects_list()['projects']}
  self.assertEqual(rows['story']['workspace_interface'],'writing');self.assertTrue(rows['story']['available'])
  self.assertEqual(rows['market']['workspace_interface'],'task')
  with self.assertRaises(ValueError):w.project('story')
 def test_shared_sources_private_annotations_and_task_directions(self):
  w=self.workspace();source=self.root/'source.md';source.write_text('工具能力原始资料\n')
  import hashlib
  w.evidence.register({'research_source_id':'sample','title':'隔离资料','media_type':'text','binding':{'kind':'local_file','locator':str(source)},'expected_fingerprint':hashlib.sha256(source.read_bytes()).hexdigest()},operation_key='source',preview_only=False)
  for project in ['market','tools']:w.evidence.link('sample',project,'测试共享来源',[],True,0,project)
  note={'project':'market','annotation_id':'private-note','research_source_id':'sample','source_revision':1,'position':{'type':'text_range','line_start':1,'line_end':1},'content_type':'owner_note','content':'只属于market的研究判断','limitations':'隔离测试，不是正式业务数据'}
  p=w.evidence.preview(note);w.evidence.save(note,0,p['preview_fingerprint'],'note')
  self.assertEqual(w.evidence.annotations('tools')['total'],0)
  snapshot={'task':'采集调研','summary':'真实任务格式的隔离测试','next_step':'核对来源','task_context':{'task_id':'review','stage':'证据核对','state':'active','direction_revision':2}}
  p=w.conversations.preview('market','current',snapshot);w.conversations.save('market','current',snapshot,0,p['preview_fingerprint'],'session')
  self.assertEqual(self.workspace().resume('market')['stage'],'证据核对')
  with self.assertRaises(ValueError):w.evidence.get('sample','story')
 def test_project_ids_cannot_overlap_domains(self):
  self.config['research_projects']['story']={'path':str(self.root/'tools'),'label':'conflict','domain':'research'};self.cfg.write_text(json.dumps(self.config))
  with self.assertRaises(ValueError):load_settings()
if __name__=='__main__':unittest.main()
