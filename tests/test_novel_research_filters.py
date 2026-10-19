import sys
import os
from tests.support import create_story
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from novel_store import Store
from novel_research import edition_references

class ResearchFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.refs=self.root/'refs'
        self.refs.mkdir()
        self.store=Store(self.root/'data')
        samples={
            'rules/srd35-dragon.md':'D&D 3.5：巨龙 职业 成长，条文需核对。',
            'rules/srd51-dragon.md':'SRD 5.1：巨龙资料。',
            'mixed.md':'D&D 3.5 巨龙 职业与 SRD 5.1 职业比较。',
            'unknown.md':'巨龙 职业资料，未提供规则版本。',
            'art/godot.md':'Godot 3.5.x：巨龙 职业图标。',
            'art/heading.md':'### 3.5 美术：巨龙 职业图标。',
        }
        for rel,body in samples.items():
            p=self.refs/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body)
        self.store.index('research',self.refs)
    def tearDown(self):
        self.tmp.cleanup()
    def test_edition_requires_explicit_reference_and_keeps_mixed(self):
        hits=self.store.search('巨龙',20,edition_filter='dnd35')['hits']
        self.assertEqual({h['path'] for h in hits},{'rules/srd35-dragon.md','mixed.md'})
        mixed=next(h for h in hits if h['path']=='mixed.md')
        self.assertEqual(set(mixed['edition_refs']),{'dnd35','srd51'})
        self.assertEqual(mixed['edition_scope'],'mixed')
        self.assertTrue(mixed['edition_evidence'])
    def test_literal_path_and_all_keywords(self):
        result=self.store.search('巨龙 职业',20,path_prefix='rules/',match_mode='all')
        self.assertEqual([h['path'] for h in result['hits']],['rules/srd35-dragon.md'])
        self.assertEqual(result['total_matching_chunks'],1)
        self.assertEqual(result['filters']['match_mode'],'all')
    def test_unknown_and_mixed_are_available(self):
        hits=self.store.search('巨龙',20,edition_filter='unknown')['hits']
        self.assertEqual({h['path'] for h in hits},{'unknown.md','art/godot.md','art/heading.md'})
        hits=self.store.search('巨龙',20,edition_filter='mixed')['hits']
        self.assertEqual([h['path'] for h in hits],['mixed.md'])
    def test_does_not_spread_document_edition_to_unmarked_chunks(self):
        p=self.refs/'overview.md'
        p.write_text('D&D 3.5 巨龙\n'+'填充\n'*500+'巨龙：没有版本的独立段落。')
        self.store.index('research',self.refs)
        hits=self.store.search('巨龙',20,edition_filter='dnd35')['hits']
        self.assertTrue(any(h['path']=='overview.md' for h in hits))
        self.assertFalse(any('独立段落' in h['body'] for h in hits))
    def test_filters_do_not_mutate_source_ids_or_versions(self):
        before=self.store.inventory()
        self.store.search('巨龙',20,edition_filter='dnd35',path_prefix='rules/')
        self.assertEqual(before,self.store.inventory())
        hit=self.store.search('巨龙',20,edition_filter='dnd35',path_prefix='rules/')['hits'][0]
        self.assertEqual(self.store.source(hit['source_id'],hit['fingerprint'])['body'],hit['body'])
    def test_invalid_filters_and_literal_metacharacters(self):
        for kwargs in ({'edition_filter':'3.5'},{'match_mode':'semantic'},
                       {'path_prefix':'../rules/'},{'path_prefix':'/rules/'},
                       {'path_prefix':'rules/../art/'},{'path_prefix':'rules\\art'}):
            with self.assertRaises(ValueError):self.store.search('巨龙',**kwargs)
        self.assertFalse(self.store.search('巨龙',path_prefix='%')['hits'])

    def test_all_supported_edition_references(self):
        for edition,text in [('srd51','SRD 5.1'),('srd52','SRD 5.2.1'),
                             ('bg3','博德之门 3'),('dos2','神界：原罪 2')]:
            self.assertEqual(edition_references('unknown.md',text)['edition_refs'],[edition])
        self.assertEqual(edition_references('unknown.md','SRD 5.2')['edition_refs'],['srd52'])
        self.assertEqual(edition_references('unknown.md','BG3 DOS2')['edition_scope'],'mixed')

    def test_path_and_version_marker_boundaries(self):
        for path in ('rules/notsrd35.md','rules/srd350.md','rules/srd35extra.md'):
            self.assertEqual(edition_references(path,'巨龙')['edition_refs'],[])
        self.assertEqual(edition_references('rules/SRD35-dragon.md','巨龙')['edition_refs'],['dnd35'])
        for body in ('Godot 3.5.x','### 3.5 章节','D&D 3.50','D&D 3.5.1'):
            self.assertEqual(edition_references('unknown.md',body)['edition_refs'],[])

    def test_cli_context_forwards_filters(self):
        root=Path(__file__).resolve().parent.parent
        create_story(self.root/'projects/sample-story')
        config=self.root/'config.json'
        config.write_text(json.dumps({'projects_dir':str(self.root/'projects'),'data_dir':str(self.store.directory),'collections':{}}))
        env=dict(os.environ,NOVEL_WORKBENCH_CONFIG=str(config),PUKNOWLEDGE_CONFIG=str(config))
        raw=subprocess.check_output([sys.executable,'-B',str(root/'scripts/novel_workbench.py'),
            '--data-dir',str(self.store.directory),'context','--project','sample-story','--query','巨龙 职业',
            '--collection','research','--edition-filter','dnd35','--path-prefix','rules/',
            '--match-mode','all'],text=True,env=env)
        result=json.loads(raw)['research']
        self.assertEqual([h['path'] for h in result['hits']],['rules/srd35-dragon.md'])
        self.assertEqual(result['filters']['edition_filter'],'dnd35')

if __name__=='__main__':unittest.main()
