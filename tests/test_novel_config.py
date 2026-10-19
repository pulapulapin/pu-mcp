import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from novel_config import load_settings
from novel_workbench import Workbench
import novel_mcp

class PortableConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.file=self.root/'settings.json'
        self.env=patch.dict(os.environ, {'NOVEL_WORKBENCH_CONFIG':str(self.file)}, clear=True)
        self.env.start()
    def tearDown(self):
        self.env.stop(); self.temp.cleanup()
    def write(self, data):
        self.file.write_text(json.dumps(data), encoding='utf-8')
    def test_relative_paths_and_workbench_use_same_external_project(self):
        self.write({'data_dir':'data','projects_dir':'projects','books_root':'books','collections':{'research':'refs'}})
        project=self.root/'projects/test';project.mkdir(parents=True)
        for name, value in {'story-contract.json':{'id':'test','core_conflict':''},'characters.json':{'characters':[]},'world.json':{'rules':[]},'timeline.json':{'events':[]},'chapters.json':{'chapters':[]}}.items():
            (project/name).write_text(json.dumps(value), encoding='utf-8')
        w=Workbench()
        self.assertEqual(w.project('test'),project)
        self.assertEqual(novel_mcp.resolve_project('test'),project)
        self.assertEqual(w.books.root,self.root/'books')
        self.assertEqual(w.collections,{'research':self.root/'refs'})
        self.assertEqual(w.status()['version'],'0.3.3')
    def test_data_environment_override(self):
        self.write({'data_dir':'old'})
        with patch.dict(os.environ, {'NOVEL_WORKBENCH_DATA':str(self.root/'override')}):
            self.assertEqual(load_settings()['data_dir'],self.root/'override')
    def test_invalid_config_is_not_silently_ignored(self):
        for data in ([],{'api_key':'unexpected'}, {'books_root':''},{'collections':[]},{'collections':{'../outside':'refs'}}):
            self.write(data)
            with self.assertRaises(ValueError):load_settings()
    def test_missing_explicit_file_fails(self):
        with self.assertRaises(FileNotFoundError):load_settings()
    def test_registered_project_outside_projects_dir(self):
        external=self.root/'books-repo/_storylab';external.mkdir(parents=True)
        for name, value in {'story-contract.json':{'id':'ext','core_conflict':''},'characters.json':{'characters':[]},'world.json':{'rules':[]},'timeline.json':{'events':[]},'chapters.json':{'chapters':[]}}.items():
            (external/name).write_text(json.dumps(value), encoding='utf-8')
        (self.root/'projects').mkdir()
        self.write({'data_dir':'data','projects_dir':'projects','projects':{'ext':'books-repo/_storylab'}})
        from novel_config import project_dirs
        self.assertEqual(load_settings()['projects'],{'ext':external})
        self.assertEqual(project_dirs(),{'ext':external})
        self.assertEqual(novel_mcp.resolve_project('ext'),external)
        self.assertEqual(Workbench().project('ext'),external)
        for bad in ([],{'../x':'p'},{'ok':''}):
            self.write({'projects':bad})
            with self.assertRaises(ValueError):load_settings()
    def test_project_symlink_escape_rejected(self):
        self.write({'projects_dir':'projects'})
        (self.root/'projects').mkdir();(self.root/'external').mkdir()
        (self.root/'projects/escape').symlink_to(self.root/'external',target_is_directory=True)
        with self.assertRaises(ValueError):novel_mcp.resolve_project('escape')

if __name__=='__main__':unittest.main()
