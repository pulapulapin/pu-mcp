import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent / 'scripts'))
from novel_store import Store
from novel_workbench import Workbench

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.refs=self.root / 'refs';self.refs.mkdir()
        self.store=Store(self.root / 'data')
        self.projects=self.root / 'projects';p=self.projects / 'test';p.mkdir(parents=True)
        for filename,data in {'story-contract.json':{'id':'test','core_conflict':'','invariants':['不能确认未决设定']},
            'characters.json':{'characters':[]},'world.json':{'rules':[]},'timeline.json':{'events':[]},'chapters.json':{'chapters':[]}}.items():
            (p / filename).write_text(json.dumps(data),encoding='utf-8')
        self.w=Workbench(self.root / 'data',self.projects,{'research':self.refs})
    def tearDown(self):self.tmp.cleanup()
    def file(self,name='srd51-classes.md',body='# 职业\n巨龙学习法师技能。\n条件与代价必须核对。\n'):
        p=self.refs / name;p.write_text(body,encoding='utf-8');return p
    def proposed(self,body='第一段原文。\n\n第二段原文。\n',baseline=0,draft='chapter-001'):
        return self.w.propose('test',draft,'测试章节',body,baseline)
    def test_repeat_import_and_chinese_search(self):
        self.file();a=self.w.index('research');b=self.w.index('research')
        self.assertEqual((a['updated'],b['unchanged'],b['updated']),(1,1,0))
        hit=self.store.search('巨龙 技能')['hits'][0]
        self.assertEqual(hit['edition'],'SRD 5.1');self.assertEqual(hit['line_start'],1)
        self.assertEqual(len(self.store.inventory()['sources']),1)
    def test_updated_source_keeps_old_snapshot(self):
        p=self.file();self.w.index('research');old=self.store.search('巨龙')['hits'][0]
        p.write_text('修订资料：骑士。',encoding='utf-8');self.w.index('research')
        self.assertFalse(self.store.search('巨龙')['hits'])
        snapshot=self.store.source(old['source_id'],old['fingerprint'])
        self.assertIn('巨龙',snapshot['body']);self.assertFalse(snapshot['current'])
    def test_deleted_source_is_not_current(self):
        p=self.file();self.w.index('research');p.unlink();self.w.index('research')
        self.assertEqual(self.store.inventory()['active_count'],0)
        self.assertFalse(self.store.search('巨龙')['hits'])
    def test_symlink_and_invalid_encoding_not_imported(self):
        outside=self.root / 'outside.md';outside.write_text('私有文本')
        (self.refs / 'escape.md').symlink_to(outside)
        (self.refs / 'bad.txt').write_bytes(b'\xff\xfe\xff')
        r=self.w.index('research');self.assertEqual(r['updated'],0);self.assertEqual(len(r['skipped']),2)
    def test_search_rejects_empty_and_has_no_sql_injection(self):
        self.file();self.w.index('research')
        with self.assertRaises(ValueError):self.store.search(' ')
        self.assertFalse(self.store.search("' OR 1=1 --")['hits'])
        self.assertEqual(self.store.inventory()['active_count'],1)
    def test_context_distinguishes_reference_and_canon(self):
        before=(self.projects / 'test/story-contract.json').read_bytes()
        self.file();self.w.index('research');result=self.w.context('test','巨龙')
        self.assertEqual(result['confirmed_context']['invariants'],['不能确认未决设定'])
        self.assertTrue(result['research']['hits']);self.assertIn('不是Canon',result['reference_policy'])
        self.assertEqual(before,(self.projects / 'test/story-contract.json').read_bytes())
    def test_resume_after_restart_and_checkpoint_conflict(self):
        self.file();self.w.index('research');hit=self.store.search('巨龙')['hits'][0]
        self.w.save_checkpoint('test','研究职业','只讨论候选','比较条件',[{'source_id':hit['source_id'],'fingerprint':hit['fingerprint']}],0)
        restarted=Workbench(self.root / 'data',self.projects,{'research':self.refs})
        self.assertEqual(restarted.resume('test')['resume_mode'],'checkpoint')
        self.assertEqual(restarted.resume('test')['task'],'研究职业')
        with self.assertRaises(ValueError):self.w.save_checkpoint('test','覆盖','摘要','下一步',[],0)
        self.assertEqual(self.store.checkpoint('test')['revision'],1)
    def test_checkpoint_unknown_stage_separated_from_project_stage(self):
        initial=self.w.resume('test')
        task='请比较三个完整的职业研究方案，不确认设定。'
        checkpoint=self.w.save_checkpoint('test',task,'接入验收','比较条件',[],0)
        restarted=Workbench(self.root / 'data',self.projects,{'research':self.refs})
        result=restarted.resume('test')
        self.assertIsNone(result['stage'])
        self.assertEqual(result['project_stage'],initial['stage'])
        self.assertEqual(result['stage_source'],'unknown')
        self.assertEqual(result['task'],task)
        self.assertEqual(result['next_step'],'比较条件')
        self.assertEqual(result['checkpoint'],checkpoint)
        contract_path=self.projects / 'test/story-contract.json'
        contract=json.loads(contract_path.read_text())
        contract['core_conflict']='隔离测试中已存在的冲突'
        contract_path.write_text(json.dumps(contract),encoding='utf-8')
        result=restarted.resume('test')
        self.assertIsNone(result['stage'])
        self.assertEqual(result['project_stage'],'主题')
        self.assertEqual(result['task'],task)
        self.assertEqual(result['checkpoint'],checkpoint)

    def test_checkpoint_rejects_missing_source(self):
        with self.assertRaises(ValueError):self.w.save_checkpoint('test','任务','摘要','下一步',[{'source_id':999,'fingerprint':'bad'}],0)
        self.assertIsNone(self.store.checkpoint('test'))
    def test_proposal_does_not_change_draft_or_canon(self):
        before={p.name:p.read_bytes() for p in (self.projects / 'test').iterdir()}
        proposal=self.proposed();self.assertIn('+第一段原文',proposal['diff'])
        self.assertEqual(self.store.list_drafts('test'),[])
        self.store.reject(proposal['id'])
        with self.assertRaises(ValueError):self.store.commit_draft(proposal['id'],'attempt')
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.projects / 'test').iterdir()})
    def test_idempotent_save_and_operation_key_reuse(self):
        p=self.proposed();first=self.store.commit_draft(p['id'],'op-1')
        self.assertEqual(first,self.store.commit_draft(p['id'],'op-1'))
        self.assertEqual(self.store.draft('test','chapter-001')['revision'],1)
        other=self.proposed('修改',1)
        with self.assertRaises(ValueError):self.store.commit_draft(other['id'],'op-1')
    def test_stale_proposal_rejected(self):
        a=self.proposed('方案甲');b=self.proposed('方案乙')
        self.store.commit_draft(a['id'],'save-a')
        with self.assertRaises(ValueError):self.store.commit_draft(b['id'],'save-b')
        self.assertEqual(self.store.draft('test','chapter-001')['body'],'方案甲')
    def test_unchanged_paragraph_and_old_version_recovery(self):
        p=self.proposed();self.store.commit_draft(p['id'],'initial')
        revised='第一段改稿。\n\n第二段原文。\n'
        p=self.proposed(revised,1);self.store.commit_draft(p['id'],'revision')
        self.assertEqual(self.store.draft('test','chapter-001')['body'],revised)
        old=self.store.draft('test','chapter-001',1)
        p=self.proposed(old['body'],2);self.store.commit_draft(p['id'],'restore')
        self.assertEqual(self.store.draft('test','chapter-001')['body'],old['body'])
        self.assertEqual(self.store.draft('test','chapter-001')['revision'],3)
    def test_concurrent_proposals_only_one_can_commit(self):
        a=self.proposed('甲');b=self.proposed('乙')
        def save(pair):
            try:return Store(self.root / 'data').commit_draft(pair[0],pair[1])
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,[(a['id'],'a'),(b['id'],'b')]))
        self.assertEqual(sum(r is not None for r in results),1)
    def test_transaction_failure_rolls_back_all_writes(self):
        p=self.proposed()
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_version BEFORE INSERT ON draft_versions BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.commit_draft(p['id'],'fail')
        self.assertEqual(self.store.list_drafts('test'),[])
        self.assertEqual(self.store.preview(p['id'])['state'],'pending')
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM operations').fetchone()[0],0)
    def test_backup_restore_drafts_research_and_checkpoint(self):
        self.file();self.w.index('research');self.w.save_checkpoint('test','研究','摘要','继续',[],0)
        p=self.proposed();self.store.commit_draft(p['id'],'save')
        backup=self.store.backup();restored=Store.restore_to_new(backup['path'],self.root / 'restored')
        self.assertEqual(restored.draft('test','chapter-001')['body'],self.store.draft('test','chapter-001')['body'])
        self.assertEqual(restored.checkpoint('test')['task'],'研究');self.assertTrue(restored.search('巨龙')['hits'])
        with self.assertRaises(ValueError):Store.restore_to_new(backup['path'],self.root / 'restored')
    def test_unknown_schema_is_not_overwritten(self):
        with self.store.connection() as db:db.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):Store(self.root / 'data')
        with sqlite3.connect(self.store.path) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],99)
    def test_project_path_escape_and_unconfigured_collection(self):
        with self.assertRaises(ValueError):self.w.context('../test','')
        with self.assertRaises(ValueError):self.w.index('/private')
        (self.projects / 'link').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):self.w.resume('link')
    def test_selected_edit_preserves_outside_text(self):
        p=self.proposed();self.store.commit_draft(p['id'],'save')
        p=self.w.propose_edit('test','chapter-001','第一段原文。','仅修改这一段。',1)
        self.assertEqual(p['body'],'仅修改这一段。\n\n第二段原文。\n')
        self.store.commit_draft(p['id'],'edit')
        self.assertEqual(self.store.draft('test','chapter-001')['body'],p['body'])
    def test_selected_edit_rejects_ambiguous_or_stale_selection(self):
        p=self.proposed('重复。重复。');self.store.commit_draft(p['id'],'save')
        with self.assertRaises(ValueError):self.w.propose_edit('test','chapter-001','重复。','新文',1)
        with self.assertRaises(ValueError):self.w.propose_edit('test','chapter-001','重复。重复。','新文',0)
    def test_punctuation_only_query_is_rejected(self):
        with self.assertRaises(ValueError):self.store.search('？？？')
    def test_parallel_first_database_initialization(self):
        path=self.root / 'fresh'
        with ThreadPoolExecutor(max_workers=8) as pool:
            stores=list(pool.map(lambda _:Store(path),range(8)))
        self.assertEqual(len(stores),8)
        with stores[0].connection() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)
    def test_search_diversifies_sources(self):
        self.file('a.md','巨龙 职业。'*2000)
        self.file('b.md','另一个来源的巨龙 职业资料。')
        self.w.index('research')
        hits=self.store.search('巨龙 职业',6)['hits']
        self.assertEqual({h['path'] for h in hits},{'a.md','b.md'})
        self.assertLessEqual(sum(h['path']=='a.md' for h in hits),2)
    def test_long_line_context_is_bounded(self):
        self.file(body='巨龙'*10000);self.w.index('research')
        hits=self.store.search('巨龙',2)['hits']
        self.assertEqual(len(hits),2)
        self.assertTrue(all(len(h['body'])<=1000 for h in hits))
    def test_markdown_export_is_not_publication(self):
        p=self.proposed();self.store.commit_draft(p['id'],'save')
        result=self.w.export('test','chapter-001')
        self.assertTrue(result['markdown'].startswith('# 测试章节\n\n'))
        self.assertFalse(result['published'])

if __name__=='__main__':unittest.main()
