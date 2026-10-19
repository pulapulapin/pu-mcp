"""Whitelist-only local workspace filesystem reader."""
import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

class WorkspaceFsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name).resolve()
  self.ws=self.root/'ws';self.ws.mkdir()
  (self.ws/'01-topics').mkdir();(self.ws/'01-topics'/'alpha.md').write_text('# Alpha\n商业化讨论\n')
  (self.ws/'03-projects').mkdir();(self.ws/'03-projects'/'demo').mkdir()
  (self.ws/'03-projects'/'demo'/'project.md').write_text('# Demo\n盈利路径\n第二行\n')
  (self.ws/'.git').mkdir();(self.ws/'.git'/'config').write_text('secret')
  (self.ws/'.venv').mkdir();(self.ws/'.venv'/'x.py').write_text('print(1)\n')
  self.outside=self.root/'outside';self.outside.mkdir();(self.outside/'leak.md').write_text('leak\n')
  self.config=self.root/'config.json'
  self.config.write_text(json.dumps({
   'data_dir':str(self.root/'data'),
   'workspaces':{'sample':{
    'path':str(self.ws),'label':'Sample','domain':'research',
    'fs_read':{'enabled':True,'readonly':True,'suffixes':['.md','.txt','.json'],
               'max_file_bytes':2000000,'deny_globs':['.git/**','.venv/**']}
   }}
  }))
  env=patch.dict(os.environ,{'NOVEL_WORKBENCH_CONFIG':str(self.config),'PUKNOWLEDGE_CONFIG':str(self.config)})
  env.start();self.addCleanup(env.stop)
  from novel_config import load_settings
  from workspace_fs import FsWorkspace
  self.settings=load_settings()
  self.fs=FsWorkspace(self.settings,'sample')

 def test_status_lists_enabled_workspace(self):
  s=self.fs.status()
  self.assertEqual(s['project'],'sample');self.assertTrue(s['readonly']);self.assertIn('.md',s['suffixes'])

 def test_list_and_read_with_fingerprint(self):
  listed=self.fs.list_files('01-topics',depth=2)
  self.assertEqual(listed['total'],1);path=listed['files'][0]['path']
  self.assertEqual(path,'01-topics/alpha.md')
  raw=(self.ws/'01-topics'/'alpha.md').read_bytes()
  fp=hashlib.sha256(raw).hexdigest()
  self.assertEqual(listed['files'][0]['fingerprint'],fp)
  page=self.fs.read_file(path,fp,0,20)
  self.assertIn('Alpha',page['text']);self.assertEqual(page['line_start'],1)

 def test_search_and_and_or(self):
  and_hits=self.fs.search('商业化 盈利',mode='and')
  self.assertEqual(and_hits['total'],0)
  or_hits=self.fs.search('商业化 盈利',mode='or')
  self.assertGreaterEqual(or_hits['total'],2)
  phrase=self.fs.search('盈利路径',mode='phrase')
  self.assertEqual(phrase['hits'][0]['path'],'03-projects/demo/project.md')

 def test_denies_git_venv_traversal_oversized_and_foreign_project(self):
  from workspace_fs import FsWorkspace
  with self.assertRaises(ValueError):self.fs.read_file('.git/config', '0'*64)
  with self.assertRaises(ValueError):self.fs.list_files('.venv',depth=1)
  with self.assertRaises(ValueError):self.fs.read_file('../outside/leak.md','0'*64)
  with self.assertRaises(ValueError):self.fs.read_file('/tmp/x.md','0'*64)
  with self.assertRaises(ValueError):FsWorkspace(self.settings,'missing')
  big=self.ws/'01-topics'/'huge.md';big.write_bytes(b'x'*(2*1024*1024+1))
  with self.assertRaises(ValueError):self.fs.open_file('01-topics/huge.md')

 def test_symlink_file_rejected_when_available(self):
  link=self.ws/'01-topics'/'link.md'
  try:link.symlink_to(self.outside/'leak.md')
  except OSError:self.skipTest('symlink unavailable')
  with self.assertRaises((ValueError,OSError)):self.fs.open_file('01-topics/link.md')
  listed=self.fs.list_files('01-topics',depth=1)
  self.assertFalse(any(x['path'].endswith('link.md') for x in listed['files']))

 def test_config_without_fs_read_is_not_listed(self):
  other=self.root/'other';other.mkdir();(other/'a.md').write_text('a\n')
  self.config.write_text(json.dumps({
   'data_dir':str(self.root/'data'),
   'workspaces':{
    'sample':{'path':str(self.ws),'label':'Sample','domain':'research',
              'fs_read':{'enabled':True,'readonly':True,'suffixes':['.md'],'max_file_bytes':1000,'deny_globs':[]}},
    'plain':{'path':str(other),'label':'Plain','domain':'research'}
   }
  }))
  from novel_config import load_settings
  from workspace_fs import FsWorkspace,list_fs_workspaces
  settings=load_settings()
  ids=[x['project'] for x in list_fs_workspaces(settings)]
  self.assertEqual(ids,['sample'])
  with self.assertRaises(ValueError):FsWorkspace(settings,'plain')

if __name__=='__main__':unittest.main()
