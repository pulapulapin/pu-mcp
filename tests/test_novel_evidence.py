import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from novel_store import Store
from novel_workbench import Workbench
from novel_evidence import ResearchSource, Annotation

TABLES = ('handoff_versions','voice_record_versions','research_annotation_versions','research_project_links','research_source_versions','research_sources')

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for project in ('a', 'b'):
            (self.root / 'projects' / project).mkdir(parents=True)
        (self.root / 'media').mkdir()
        self.video = self.root / 'media/video.mp4'
        self.video.write_bytes(b'fixture, not a playable video')
        self.fp = hashlib.sha256(self.video.read_bytes()).hexdigest()
        cfg = self.root / 'config.json'
        cfg.write_text(json.dumps({'data_dir': str(self.root / 'db'), 'projects_dir': str(self.root / 'projects'), 'research_roots': [str(self.root / 'media')]}))
        env = patch.dict(os.environ, {'NOVEL_WORKBENCH_CONFIG': str(cfg)}, clear=True)
        env.start(); self.addCleanup(env.stop)
        self.w = Workbench()
        self.e = self.w.evidence
        self.source = {'research_source_id':'video-test','title':'测试视频','media_type':'video',
                       'binding':{'kind':'local_file','locator':str(self.video)}, 'expected_fingerprint':self.fp}
    def register(self, **changes):
        return self.e.register({**self.source, **changes}, operation_key='register', preview_only=False)
    def linked(self):
        self.register()
        for project in ('a','b'):
            self.e.link('video-test', project, '研究目的'+project, [], True, 0, 'link')
    def annotation(self, project='a', **changes):
        return {'annotation_id':'note','project':project,'research_source_id':'video-test','source_revision':1,
                'position':{'type':'time_range','start_ms':1000,'end_ms':2000},'content_type':'ai_summary',
                'content':'分析样本，不代表真实视频内容','coverage':'sample','limitations':'仅程序测试，未观看媒体',**changes}
    def save(self, a, key='save'):
        p = self.e.preview(a)
        return self.e.save(a, p['baseline'], p['preview_fingerprint'], key)
    def test_preview_no_write_and_exact_retry(self):
        p = self.e.register(self.source)
        self.assertFalse(p['saved'])
        self.assertEqual(self.e.list_sources('a')['total'], 0)
        first = self.register()
        self.assertEqual(first, self.register())
        with self.w.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM research_source_versions').fetchone()[0],1)
        with self.assertRaises(ValueError): self.register(title='different request')
    def test_cross_project_isolation_history_diff_and_retry(self):
        self.linked()
        a = self.annotation()
        b = self.annotation('b', analysis='项目b的判断')
        self.save(a); self.save(b)
        changed = {**a, 'analysis':'修订项目a的判断'}
        p = self.e.preview(changed)
        self.assertIn('修订项目a', p['diff'])
        second = self.e.save(changed,p['baseline'],p['preview_fingerprint'],'v2')
        self.assertEqual(second,self.e.save(changed,1,p['preview_fingerprint'],'v2'))
        self.assertEqual(self.e.annotations('b')['annotations'][0]['annotation']['analysis'],'项目b的判断')
        self.assertEqual(self.e.annotations('a',annotation_id='note',revision=1)['annotations'][0]['annotation']['analysis'],'')
        with self.assertRaises(ValueError): self.e.save(a,1,self.e.preview(a)['preview_fingerprint'],'stale')
    def test_private_source_hidden_by_id_list_search_and_link(self):
        self.register(scope='project', owner_project='a')
        self.assertEqual(self.e.list_sources('b')['total'],0)
        with self.assertRaises(ValueError): self.e.get('video-test','b')
        with self.assertRaises(ValueError): self.e.link('video-test','b','purpose',[],True,0,'link')
        with self.assertRaises(ValueError): self.e.annotations('b',source_id='video-test')
        self.assertEqual(self.e.annotations('b')['total'],0)
    def test_duplicate_binding_and_media_ranges(self):
        self.linked()
        with self.assertRaises(ValueError): self.register(research_source_id='alias')
        for pos in ({'type':'time_range','start_ms':2000,'end_ms':1000}, {'type':'time_range','start_ms':1,'end_ms':1}, {'type':'time_range','start_ms':1,'end_ms':2,'page_start':1}, {'type':'pdf_page','page_start':1,'page_end':1}):
            with self.assertRaises(ValueError): self.e.preview(self.annotation(position=pos))
        with self.assertRaises(ValueError): self.e.preview(self.annotation(content_type='sampled_subtitle',coverage='complete_transcript'))
        with self.assertRaises(ValueError): self.e.preview(self.annotation(content_type='ai_summary',coverage='complete_transcript'))
    def test_file_change_stale_evidence_and_withdraw(self):
        self.linked(); a=self.annotation(); self.save(a)
        self.video.write_bytes(b'changed')
        self.assertTrue(self.e.get('video-test','a')['stale'])
        self.assertTrue(self.e.annotations('a')['annotations'][0]['stale'])
        with self.assertRaises(ValueError): self.e.preview(a)
        withdrawn={**a,'state':'outdated'}
        result=self.save(withdrawn,'outdated')
        self.assertEqual(result['revision'],2)
        self.assertEqual(self.e.annotations('a',annotation_id='note',revision=1)['annotations'][0]['annotation']['state'],'active')
    def test_unlink_preserves_source_and_other_project(self):
        self.linked(); self.save(self.annotation('b'))
        self.e.link('video-test','a','停用',[],False,1,'unlink')
        with self.assertRaises(ValueError): self.e.preview(self.annotation())
        self.assertEqual(self.e.annotations('b')['total'],1)
        self.assertEqual(self.e.get('video-test','a')['revision'],1)
    def test_symlink_escape_and_unknown_project(self):
        link=self.video.parent/'link.mp4';link.symlink_to(self.video)
        with self.assertRaises(ValueError): self.register(binding={'kind':'local_file','locator':str(link)})
        outside=self.root/'outside.mp4';outside.write_bytes(b'outside')
        with self.assertRaises(ValueError): self.register(binding={'kind':'local_file','locator':str(outside)})
        with self.assertRaises(ValueError): self.e.list_sources('missing')
        with self.assertRaises(ValueError): self.register(scope='project',owner_project='missing')
    def test_source_revisions_restart_and_metadata_only(self):
        self.register()
        self.e.register({**self.source,'title':'新标题'},baseline=1,operation_key='v2',preview_only=False)
        reopened=Workbench().evidence
        self.assertEqual(reopened.get('video-test','a',1)['source']['title'],'测试视频')
        self.assertEqual(reopened.get('video-test','a')['source']['title'],'新标题')
        with self.w.store.connection() as db:
            data=db.execute('SELECT body FROM research_source_versions').fetchall()
            self.assertNotIn('fixture, not a playable video',str([tuple(x) for x in data]))
    def test_url_no_fetch_and_pdf_declaration(self):
        source={**self.source,'research_source_id':'remote','binding':{'kind':'url','locator':'https://example.invalid/video'},'expected_fingerprint':''}
        self.e.register(source,operation_key='url',preview_only=False)
        self.assertEqual(self.e.get('remote','a')['source_state'],'unverified_remote')
        with self.assertRaises(ValueError): self.register(binding={'kind':'url','locator':'https://user:pw'+'@example.invalid/video'})
        pdf=self.video.parent/'test.pdf';pdf.write_bytes(b'pdf fixture')
        source={**self.source,'research_source_id':'pdf','media_type':'pdf','binding':{'kind':'local_file','locator':str(pdf)},'expected_fingerprint':hashlib.sha256(pdf.read_bytes()).hexdigest()}
        self.e.register(source,operation_key='pdf',preview_only=False)
        self.e.link('pdf','a','purpose',[],True,0,'link')
        a=self.annotation(research_source_id='pdf',position={'type':'pdf_page','page_start':2,'page_end':3})
        self.assertEqual(self.e.preview(a)['evidence']['locator_verification'],'declared_unverified')
    def test_legacy_text_binding_excerpts_and_search_isolation(self):
        refs=self.root/'refs';refs.mkdir();(refs/'a.md').write_text('第一行\n第二行证据\n')
        self.w.store.index('fixture',refs)
        old=self.w.store.inventory()['sources'][0]
        source={**self.source,'research_source_id':'text','media_type':'article','binding':{'kind':'indexed_text','locator':str(old['id'])},'expected_fingerprint':old['fingerprint']}
        self.e.register(source,operation_key='text',preview_only=False)
        self.e.link('text','a','purpose',[],True,0,'link')
        a=self.annotation(research_source_id='text',position={'type':'text_range','line_start':2,'line_end':2},content_type='original_excerpt',content='第二行证据',tags=['开篇'])
        self.save(a)
        self.assertEqual(self.e.annotations('a',query='证据',tag='开篇')['total'],1)
        self.assertEqual(self.e.annotations('b',query='证据')['total'],0)
        with self.assertRaises(ValueError): self.e.preview({**a,'content':'伪造原文'})
        with self.assertRaises(ValueError): self.e.preview({**a,'position':{'type':'text_range','char_start':0,'char_end':1000}})
    def test_tamper_preview_and_atomic_failure(self):
        self.linked(); a=self.annotation();p=self.e.preview(a)
        with self.assertRaises(ValueError): self.e.save({**a,'content':'tampered'},0,p['preview_fingerprint'],'save')
        with self.w.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_annotation BEFORE INSERT ON research_annotation_versions BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(Exception): self.e.save(a,0,p['preview_fingerprint'],'save')
        self.assertEqual(self.e.annotations('a')['total'],0)
        with self.w.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM operations WHERE project LIKE 'evidence-annotation:%'").fetchone()[0],0)
    def test_concurrent_annotation_update_only_one_wins(self):
        self.linked(); self.save(self.annotation())
        proposals=[self.e.preview(self.annotation(analysis=str(i))) for i in range(2)]
        def run(p):
            try: return self.e.save(p['annotation'],1,p['preview_fingerprint'],'save-'+p['annotation']['analysis'])
            except ValueError: return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(x is not None for x in pool.map(run,proposals)),1)
    def test_schema3_migration_preserves_old_tables_and_failure_rolls_back(self):
        with self.w.store.connection(write=True) as db:
            for name in TABLES: db.execute('DROP TABLE '+name)
            db.execute('DROP TABLE IF EXISTS knowledge_versions');db.execute('PRAGMA user_version=3')
            db.execute("INSERT INTO checkpoints VALUES('a',8,'task','summary','next','[]','date')")
            names=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            before={name:[tuple(row) for row in db.execute('SELECT * FROM '+name)] for name in names}
        def broken(db):
            db.execute('CREATE TABLE bad(x)');raise RuntimeError('fixture')
        with patch('novel_evidence.schema',broken), self.assertRaises(RuntimeError): Store(self.w.store.directory)
        with self.w.store.connection() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='bad'").fetchone())
        Store(self.w.store.directory)
        with self.w.store.connection() as db:
            after={name:[tuple(row) for row in db.execute('SELECT * FROM '+name)] for name in names}
            self.assertEqual(before,after)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)
        self.assertTrue(list((self.w.store.directory/'backups').glob('*.sqlite3')))

    def test_book_location_and_original_evidence(self):
        from novel_books import Books
        book=self.root/'media/book.txt'
        book.write_text('第一章 开始\n人物学习。\n第二章 后来\n人物行动。\n')
        self.w.books=Books(self.w.store,book.parent,{'fixture':('测试小说','book.txt')})
        fp=hashlib.sha256(book.read_bytes()).hexdigest()
        self.w.books.index('fixture',fp)
        source={**self.source,'research_source_id':'book','media_type':'book','binding':{'kind':'reference_book','locator':'fixture'},'expected_fingerprint':fp}
        self.e.register(source,operation_key='book',preview_only=False)
        self.e.link('book','a','purpose',[],True,0,'link')
        a=self.annotation(research_source_id='book',position={'type':'book_range','chapter_id':'1:1','line_start':2,'line_end':2},content_type='original_excerpt',content='人物学习。')
        self.assertEqual(self.save(a)['revision'],1)
        reader=self.e.annotations('a')['annotations'][0]['evidence_reader']
        self.assertEqual(reader['book_id'],'fixture')
        for pos in ({'type':'book_range','chapter_id':'1:1','char_start':0,'char_end':99999}, {'type':'book_range','chapter_id':'2:1','line_start':2,'line_end':2}):
            with self.assertRaises(ValueError): self.e.preview({**a,'position':pos})
        with self.assertRaises(ValueError): self.e.preview({**a,'content':'伪造原文'})
    def test_backup_restore_includes_shared_sources_and_annotations(self):
        self.linked();self.save(self.annotation())
        original=self.e.annotations('a')['annotations'][0]['annotation']
        restored=Store.restore_to_new(self.w.store.backup()['path'],self.root/'restored')
        self.w.store=restored;self.e.store=restored
        self.assertEqual(self.e.annotations('a')['annotations'][0]['annotation'],original)
        self.assertEqual(self.e.get('video-test','b')['project_link']['purpose'],'研究目的b')
    def test_updated_source_keeps_original_evidence_stale(self):
        self.linked();self.save(self.annotation())
        self.video.write_bytes(b'new bytes')
        changed={**self.source,'expected_fingerprint':hashlib.sha256(self.video.read_bytes()).hexdigest()}
        self.e.register(changed,baseline=1,operation_key='source-v2',preview_only=False)
        self.assertTrue(self.e.get('video-test','a',1)['stale'])
        self.assertFalse(self.e.get('video-test','a')['stale'])
        self.assertTrue(self.e.annotations('a')['annotations'][0]['stale'])
        with self.assertRaises(ValueError): self.e.register(changed,baseline=1,operation_key='stale',preview_only=False)

if __name__=='__main__': unittest.main()
