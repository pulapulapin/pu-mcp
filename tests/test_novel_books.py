import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from novel_store import Store
from novel_books import Books

class BookTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.store=Store(self.root/'db')
        self.books=Books(self.store,self.root,{'test':('测试作品','test.txt')})
        self.path=self.root/'test.txt'
        self.write('第001章初生\n甲财富乙。\n\n第2章成长\n丙职业丁。\n第2章重复\n终。\n')
    def tearDown(self): self.tmp.cleanup()
    def write(self,text,encoding='gb18030'):
        self.path.write_bytes(text.encode(encoding))
        self.fp=hashlib.sha256(self.path.read_bytes()).hexdigest()
    def indexed(self): return self.books.index('test',self.fp)
    def test_encoding_positions_and_duplicate_numbers(self):
        before=self.path.read_bytes()
        result=self.indexed()
        self.assertEqual(result['encoding'],'gb18030')
        self.assertEqual(result['chapter_count'],3)
        directory=self.books.structure('test',limit=1)
        self.assertEqual(directory['next_offset'],1)
        self.assertIn('重复',result['warnings'][0])
        excerpt=self.books.read('test','1:1',self.fp,max_chars=12)
        decoded=self.path.read_bytes()[excerpt['byte_start']:excerpt['byte_end']].decode('gb18030')
        self.assertEqual(decoded,excerpt['body'])
        self.assertTrue(excerpt['truncated'])
        page=self.books.read('test','1:1',self.fp,excerpt['next_char_offset'],6000)
        self.assertEqual(excerpt['body']+page['body'],before[:directory['entries'][0]['byte_end']].decode('gb18030'))
        self.assertEqual(self.path.read_bytes(),before)
    def test_utf8_bom_and_search_continuation(self):
        self.write('前言\n第1章财富\n内容\n第2章职业\n财富\n第3章结尾\n财富\n','utf-8-sig')
        self.indexed()
        result=self.books.search('test','财富',self.fp,limit=1)
        self.assertFalse(result['complete'])
        second=self.books.search('test','财富',self.fp,start_ordinal=result['next_start_ordinal'])
        self.assertEqual(second['hits'][0]['chapter_id'],'1:2')
        self.assertTrue(second['complete'])
    def test_bom_at_first_chapter_byte_locator(self):
        self.write('第1章初生\n正文。\n','utf-8-sig');self.indexed()
        result=self.books.read('test','1:1',self.fp,max_chars=4)
        self.assertEqual(result['byte_start'],3)
        self.assertEqual(self.path.read_bytes()[result['byte_start']:result['byte_end']].decode('utf-8'),result['body'])
    def test_stale_index_refuses_read_and_search_and_reindexes(self):
        self.indexed();old=self.fp
        self.write('第1章新\n不同原文\n')
        self.assertEqual(self.books.list()['books'][0]['index_state'],'stale')
        with self.assertRaises(ValueError): self.books.read('test','1:1',old)
        with self.assertRaises(ValueError): self.books.search('test','财富',old)
        with self.assertRaises(ValueError): self.books.index('test',self.fp,baseline=0)
        self.assertEqual(self.books.index('test',self.fp,baseline=1)['revision'],2)
        with self.assertRaises(ValueError): self.books.read('test','1:1',old)
    def test_manual_index_correction_and_retry(self):
        self.indexed()
        edits=[{'line':6,'kind':'ignore'}]
        self.books.index('test',self.fp,1,edits)
        self.assertTrue(self.books.index('test',self.fp,1,edits)['unchanged'])
        self.assertEqual(self.books.structure('test')['total_entries'],2)
        with self.assertRaises(ValueError): self.books.index('test',self.fp,0,edits)
    def test_no_text_storage_and_bounds(self):
        self.indexed()
        with self.store.connection() as db:
            columns={r[1] for r in db.execute('PRAGMA table_info(reference_chapters)')}
        self.assertNotIn('body',columns)
        with self.assertRaises(ValueError): self.books.read('test','1:1',self.fp,max_chars=6001)
        with self.assertRaises(ValueError): self.books.search('test','x',self.fp,max_chapters=101)
        with self.assertRaises(ValueError): self.books.structure('../escape')
    def test_symlink_and_oversized_line(self):
        self.path.unlink();self.path.symlink_to(self.root/'outside.txt')
        with self.assertRaises(ValueError): self.books.index('test',self.fp)
        self.path.unlink();self.write('第1章\n'+'甲'*70000)
        with self.assertRaises(ValueError): self.indexed()
    def test_volume_and_contents_are_not_readable_chapters(self):
        self.write('第1章初\n第2章中\n第3章末\n\n第一卷 开始\n第1章初\n内容\n第七卷梦眠第四百二十章幽幻\n内容\n')
        self.indexed()
        directory=self.books.structure('test')
        self.assertEqual(directory['entries'][0]['kind'],'contents')
        self.assertEqual(directory['entries'][-1]['kind'],'chapter')
        with self.assertRaises(ValueError): self.books.read('test','1:1',self.fp)
    def legacy(self):
        with self.store.connection(write=True) as db:
            for name in ('handoff_versions','voice_record_versions','research_annotation_versions','research_project_links','research_source_versions','research_sources'): db.execute("DROP TABLE " + name)
            for table in ('reading_progress','source_metadata','reference_registry','reference_chapters','reference_indexes'):db.execute('DROP TABLE '+table)
            db.execute('DROP TABLE IF EXISTS knowledge_versions');db.execute('PRAGMA user_version=1')
            db.execute("INSERT INTO checkpoints VALUES('dnd',1,'任务','摘要','下一步','[]','date')")
    def test_migration_backup_and_legacy_restore(self):
        self.legacy()
        backup=self.store.backup()['path']
        upgraded=Store(self.store.directory)
        self.assertEqual(upgraded.checkpoint('dnd')['revision'],1)
        with upgraded.connection() as db: self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)
        self.assertGreaterEqual(len(list((self.store.directory/'backups').glob('*.sqlite3'))),2)
        restored=Store.restore_to_new(backup,self.root/'restored')
        self.assertEqual(restored.checkpoint('dnd')['task'],'任务')
    def test_migration_failure_is_atomic(self):
        self.legacy()
        def broken(db):
            db.execute('CREATE TABLE should_rollback(x)')
            raise RuntimeError('migration failed')
        with patch('novel_books.schema',broken),self.assertRaises(RuntimeError): Store(self.store.directory)
        with self.store.connection() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='should_rollback'").fetchone())
        self.assertEqual(self.store.checkpoint('dnd')['revision'],1)

class WorkSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=Store(self.root/'db');self.refs=self.root/'refs';self.refs.mkdir()
    def tearDown(self): self.tmp.cleanup()
    def search(self,text,work='green-dragon-doctor',query='开篇'):
        (self.refs/'comparison.md').write_text(text,encoding='utf-8')
        self.store.index('research',self.refs)
        return self.store.search(query,collection='research',match_mode='all',work_id=work)
    def test_rows_do_not_cross_associate(self):
        result=self.search('| 作品 | 阶段 |\n| --- | --- |\n| 绿龙筑巢记 | 开篇 |\n| 绿龙博士 | 作者公告 |')
        self.assertEqual(result['hits'],[])
        self.assertEqual(result['related_documents'][0]['evidence_relation'],'related_document')
    def test_positive_work_table_column_has_no_other_cells(self):
        result=self.search('| 项目 | 绿龙博士 | 黑龙法典 |\n| --- | --- | --- |\n| 开篇 | 观察龙妈 | 灰烬出生 |')
        self.assertEqual(len(result['hits']),1)
        hit=result['hits'][0]
        self.assertIn('观察龙妈',hit['body']);self.assertNotIn('灰烬',hit['body'])
        self.assertEqual(hit['column_indexes'],[0,1]);self.assertEqual(hit['line_start'],3)
    def test_comparison_mention_cannot_reassign_another_work_column(self):
        result=self.search('| 项目 | 黑龙法典 |\n| --- | --- |\n| 开篇 | 与绿龙博士相比，主角更独立 |')
        self.assertEqual(result['hits'],[])
        self.assertTrue(result['related_documents'])
    def test_prose_mention_cannot_be_used_as_work_identifier_cell(self):
        result=self.search('| 讨论 | 评论 |\n| --- | --- |\n| 与绿龙博士相比 | 开篇更有趣 |')
        self.assertEqual(result['hits'],[])
    def test_sections_do_not_cross_associate(self):
        result=self.search('## 绿龙博士\n开篇观察。\n\n## 黑龙法典\n开篇战斗。\n')
        self.assertEqual(len(result['hits']),1);self.assertNotIn('战斗',result['hits'][0]['body'])
    def test_explicit_work_query_and_legacy_compatible(self):
        result=self.search('| 作品 | 主题 |\n| --- | --- |\n| 绿龙博士 | 开篇观察 |',query='绿龙博士 开篇')
        self.assertEqual(len(result['hits']),1)
        self.assertEqual(len(self.store.search('绿龙博士 开篇',match_mode='all')['hits']),1)
    def test_each_configured_work_has_positive_and_negative(self):
        titles={'green-dragon-doctor':'绿龙博士','black-dragon-code':'黑龙法典','frost-wings':'霜寒之翼','green-dragon-nest':'绿龙筑巢记'}
        text='| 作品 | 主题 |\n| --- | --- |\n'+'\n'.join(f'| {title} | 开篇{work} |' for work,title in titles.items())
        for work,title in titles.items():
            result=self.search(text,work)
            self.assertEqual(len(result['hits']),1)
            self.assertEqual(result['hits'][0]['work_title'],title)
    def test_changed_source_uses_current_units(self):
        old=self.search('## 绿龙博士\n开篇观察。')['hits'][0]['fingerprint']
        result=self.search('## 黑龙法典\n开篇观察。\n\n绿龙博士。')
        self.assertEqual(result['hits'],[])
        self.assertEqual(self.store.source(1,old)['body'],'## 绿龙博士\n开篇观察。')

if __name__=='__main__': unittest.main()
