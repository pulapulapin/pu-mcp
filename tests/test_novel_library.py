import hashlib,json,sys,tempfile,unittest,sqlite3
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from novel_store import Store
from novel_books import Books
from novel_library import register,set_active,metadata,set_metadata,record_progress,progress,inspect_file

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.store=Store(self.root/'db');self.books=Books(self.store,self.root)
        self.file=self.root/'new.txt';self.file.write_text('第一章 开始\n研究学习。\n第二章 成长\n人物行动。\n第三章 结果\n后续。\n',encoding='utf-8')
        self.fp=hashlib.sha256(self.file.read_bytes()).hexdigest()
    def tearDown(self):self.temp.cleanup()
    def registered(self):return register(self.books,'new-book','新小说','new.txt',self.fp,0)
    def indexed(self):
        self.registered();self.books.index('new-book',self.fp)
    def test_register_inspect_restart_and_disable(self):
        self.assertEqual(inspect_file(self.books,'new.txt')['fingerprint'],self.fp)
        result=self.registered();self.assertEqual(result['revision'],1)
        self.assertTrue(register(self.books,'new-book','新小说','new.txt',self.fp,0)['unchanged'])
        reopened=Books(Store(self.store.directory),self.root);self.assertIn('new-book',reopened.catalog)
        set_active(reopened,'new-book',False,1)
        with self.assertRaises(ValueError):reopened.path('new-book')
        self.assertFalse(next(b for b in reopened.list()['books'] if b['book_id']=='new-book')['active'])
        set_active(reopened,'new-book',True,2);self.assertEqual(reopened.path('new-book'),self.file)
    def test_registration_boundary_alias_and_conflict(self):
        for path in ('../new.txt',str(self.file)):
            with self.assertRaises(ValueError):register(self.books,'new-book','新小说',path,self.fp,0)
        self.registered()
        with self.assertRaises(ValueError):register(self.books,'alias','另一ID','new.txt',self.fp,0)
        with self.assertRaises(ValueError):register(self.books,'new-book','新标题','new.txt',self.fp,0)
        other=self.root/'linked.txt';other.symlink_to(self.file)
        with self.assertRaises(ValueError):inspect_file(self.books,'linked.txt')
    def test_progress_modes_idempotency_and_not_recorded(self):
        self.indexed()
        args=(self.books,'new-book',['1:1'],self.fp,'complete','首章完整阅读',0,'first')
        record_progress(*args);self.assertTrue(record_progress(*args)['reused'])
        record_progress(self.books,'new-book',['1:2'],self.fp,'sampled','抽样',1,'sample')
        record_progress(self.books,'new-book',['1:3'],self.fp,'keyword_hit','关键词命中',2,'keyword')
        info=progress(self.books,'new-book');self.assertEqual([e['status'] for e in info['entries']],['complete','sampled','keyword_hit'])
        self.assertEqual(info['continuous_complete_chapter_ids'],['1:1'])
        with self.assertRaises(ValueError):record_progress(self.books,'new-book',['1:1'],self.fp,'sampled','过期',0,'stale')
    def test_progress_source_change_and_new_index(self):
        self.indexed();record_progress(self.books,'new-book',['1:1'],self.fp,'complete','已读',0,'first')
        self.file.write_text(self.file.read_text()+'新段落。')
        self.assertTrue(progress(self.books,'new-book')['stale'])
        fp=hashlib.sha256(self.file.read_bytes()).hexdigest();self.books.index('new-book',fp,1)
        record_progress(self.books,'new-book',['2:2'],fp,'sampled','新版本抽样',1,'new-version')
        info=progress(self.books,'new-book');self.assertEqual(info['entries'][0]['status'],'not_recorded')
    def test_source_metadata_filter_and_fingerprint_expiry(self):
        refs=self.root/'refs';refs.mkdir();source=refs/'game.md';source.write_text('无冬之夜 职业研究。')
        self.store.index('game-research',refs);hit=self.store.search('无冬之夜')['hits'][0];sid=hit['source_id'];fp=hit['fingerprint']
        self.assertEqual(self.store.search('职业',edition_filter='dnd35')['hits'],[])
        set_metadata(self.store,sid,fp,'game','无冬之夜2','dnd35','规则说明页，来源待核','未独立验证',0)
        hit=self.store.search('职业',edition_filter='dnd35')['hits'][0]
        self.assertEqual(hit['edition_evidence'][-1]['basis'],'source_declaration_unverified')
        self.assertEqual(metadata(self.store,sid)['revision'],1)
        source.write_text('无冬之夜 职业研究已更新。');self.store.index('game-research',refs)
        self.assertEqual(self.store.search('职业',edition_filter='dnd35')['hits'],[])
        self.assertFalse(metadata(self.store,sid,fp)['current'])
    def test_new_editions_and_unknown_without_name_inference(self):
        refs=self.root/'refs';refs.mkdir();(refs/'game.md').write_text('开拓者 职业研究。');self.store.index('games',refs)
        hit=self.store.search('职业')['hits'][0];self.assertEqual(hit['edition_scope'],'unknown')
        set_metadata(self.store,hit['source_id'],hit['fingerprint'],'game','开拓者','pathfinder1e','手动核对的来源位置','',0)
        self.assertEqual(len(self.store.search('职业',edition_filter='pathfinder1e')['hits']),1)
    def test_dynamic_work_scoped_search(self):
        self.registered();refs=self.root/'refs';refs.mkdir();(refs/'fiction.md').write_text('# 新小说\n\n开篇研究学习。\n')
        self.store.index('research',refs)
        result=self.store.search('开篇',work_id='new-book');self.assertEqual(result['hits'][0]['work_title'],'新小说')
    def test_disabled_other_work_still_prevents_false_attribution(self):
        self.registered();set_active(self.books,'green-dragon-doctor',False,0)
        refs=self.root/'refs';refs.mkdir();(refs/'fiction.md').write_text('# 新小说\n\n开篇比较绿龙博士。\n')
        self.store.index('research',refs)
        self.assertEqual(self.store.search('开篇',work_id='new-book')['hits'],[])
    def test_progress_pagination(self):
        self.indexed();result=progress(self.books,'new-book',0,1)
        self.assertEqual(len(result['entries']),1);self.assertEqual(result['next_offset'],1)
        self.assertEqual(result['entries'][0]['status'],'not_recorded')
    def test_metadata_conflict_and_missing_version(self):
        refs=self.root/'refs';refs.mkdir();(refs/'game.md').write_text('职业研究。');self.store.index('research',refs)
        hit=self.store.search('职业')['hits'][0];sid=hit['source_id'];fp=hit['fingerprint']
        set_metadata(self.store,sid,fp,'game','游戏','unknown','来源位置','',0)
        with self.assertRaises(ValueError):set_metadata(self.store,sid,fp,'game','游戏','dnd35','另一声明','',0)
        with self.assertRaises(ValueError):metadata(self.store,sid,'bad')
    def test_schema2_migration_preserves_data_and_rolls_back(self):
        with self.store.connection(write=True) as db:
            for name in ('handoff_versions','voice_record_versions','research_annotation_versions','research_project_links','research_source_versions','research_sources'):db.execute('DROP TABLE '+name)
            for name in ('reading_progress','source_metadata','reference_registry'):db.execute('DROP TABLE '+name)
            db.execute('DROP TABLE IF EXISTS knowledge_versions');db.execute('PRAGMA user_version=2')
            db.execute("INSERT INTO checkpoints VALUES('dnd',3,'task','summary','next','[]','date')")
        def broken(db):
            db.execute('CREATE TABLE bad(x)');raise RuntimeError()
        with patch('novel_library.schema',broken),self.assertRaises(RuntimeError):Store(self.store.directory)
        with self.store.connection() as db:self.assertEqual(db.execute('pragma user_version').fetchone()[0],2)
        updated=Store(self.store.directory);self.assertEqual(updated.checkpoint('dnd')['revision'],3)
        with updated.connection() as db:self.assertEqual(db.execute('pragma user_version').fetchone()[0],8)

if __name__=='__main__':unittest.main()
