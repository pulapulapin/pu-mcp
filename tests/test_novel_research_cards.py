import json
from pathlib import Path
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'scripts'))
from novel_store import Store

class ResearchCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.store=Store(self.root/'data')
        self.card={'card_id':'dragon-class','title':'巨龙职业研究测试',
            'source_locator':'https://example.invalid/rules#dragon','rule_edition':'dnd35',
            'source_kind':'secondary','retrieved_on':'2026-10-09',
            'summary':'测试资料：巨龙 职业 成长的关系需核对。',
            'applicability':'只用于工具测试，不能作为小说设定。',
            'open_questions':['原始条文在哪一节？'],'excerpt':''}
    def tearDown(self):self.tmp.cleanup()
    def save(self,card=None,baseline='',key='import-1'):
        return self.store.save_research_card(card or self.card,baseline,key)
    def test_preview_is_read_only_then_save_search_read(self):
        before=self.store.inventory()
        preview=self.store.preview_research_card(self.card)
        self.assertIn('+',preview['diff'])
        self.assertEqual(self.store.inventory(),before)
        saved=self.save()
        hit=self.store.search('巨龙 职业 成长',edition_filter='dnd35',match_mode='all')['hits'][0]
        self.assertEqual(hit['source_id'],saved['source_id'])
        self.assertEqual(hit['research_card']['source_locator'],self.card['source_locator'])
        self.assertIn('未独立核验',hit['evidence_status'])
        source=self.store.source(saved['source_id'])
        self.assertEqual(source['research_card']['rule_edition'],'dnd35')
        self.assertFalse(saved['canon'])
    def test_idempotence_and_operation_key_conflict(self):
        first=self.save()
        self.assertEqual(first,self.save())
        changed={**self.card,'summary':'修改摘要'}
        with self.assertRaises(ValueError):self.save(changed,key='import-1')
        self.assertEqual(self.store.source(first['source_id'])['fingerprint'],first['fingerprint'])
    def test_update_keeps_id_and_old_snapshot_and_blocks_stale(self):
        first=self.save()
        changed={**self.card,'summary':'修订后的巨龙职业资料'}
        preview=self.store.preview_research_card(changed)
        self.assertEqual(preview['baseline_fingerprint'],first['fingerprint'])
        with self.assertRaises(ValueError):self.save(changed,baseline='',key='import-2')
        second=self.save(changed,first['fingerprint'],'import-2')
        self.assertEqual(first['source_id'],second['source_id'])
        self.assertNotEqual(first['fingerprint'],second['fingerprint'])
        old=self.store.source(first['source_id'],first['fingerprint'])
        self.assertIn(self.card['summary'],old['body'])
        self.assertEqual(old['research_card']['source_locator'],self.card['source_locator'])
    def test_same_content_new_operation_does_not_add_versions(self):
        first=self.save()
        second=self.save(baseline=first['fingerprint'],key='repeat')
        self.assertEqual(second['fingerprint'],first['fingerprint'])
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM source_versions').fetchone()[0],1)
    def test_declared_edition_does_not_become_verification(self):
        saved=self.save()
        hit=self.store.search('巨龙',edition_filter='dnd35')['hits'][0]
        self.assertTrue(any(e['basis']=='research_card_declaration' for e in hit['edition_evidence']))
        self.assertEqual(hit['research_card']['verification_status'],'unverified')
        self.assertFalse(hit['research_card']['canon'])
    def test_rejects_missing_provenance_and_forged_confirmation(self):
        for change in ({'source_locator':''},{'source_locator':'   '},
                       {'rule_edition':'confirmed'},{'canon':True},
                       {'retrieved_on':'not-a-date'},{'card_id':'../evil'}):
            with self.assertRaises(ValueError):self.save({**self.card,**change})
        self.assertFalse(self.store.inventory()['sources'])
    def test_reserved_collection_cannot_be_reindexed(self):
        saved=self.save()
        refs=self.root/'empty';refs.mkdir()
        with self.assertRaises(ValueError):self.store.index('research-cards',refs)
        self.assertEqual(self.store.source(saved['source_id'])['fingerprint'],saved['fingerprint'])
    def test_restart_backup_and_checkpoint_reference(self):
        saved=self.save()
        self.store.save_checkpoint('test','研究','摘要','继续',
            [{'source_id':saved['source_id'],'fingerprint':saved['fingerprint']}],0)
        restarted=Store(self.store.directory)
        self.assertEqual(restarted.source(saved['source_id'])['research_card']['title'],self.card['title'])
        restored=Store.restore_to_new(self.store.backup()['path'],self.root/'restored')
        self.assertEqual(restored.source(saved['source_id'])['fingerprint'],saved['fingerprint'])
        self.assertEqual(restored.checkpoint('test')['sources'][0]['fingerprint'],saved['fingerprint'])
    def test_save_failure_rolls_back_source_chunks_and_operation(self):
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_card BEFORE INSERT ON chunks BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(Exception):self.save()
        with self.store.connection() as db:
            for table in ('sources','source_versions','chunks','operations'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_failed_update_keeps_old_card_chunks_and_operations(self):
        saved=self.save()
        before=self.store.source(saved['source_id'])
        hit_before=self.store.search('巨龙',collection='research-cards')
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_update BEFORE INSERT ON chunks BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(Exception):
            self.save({**self.card,'summary':'不应保存'},saved['fingerprint'],'import-2')
        self.assertEqual(self.store.source(saved['source_id']),before)
        self.assertEqual(self.store.search('巨龙',collection='research-cards'),hit_before)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM source_versions').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM operations').fetchone()[0],1)

    def test_concurrent_updates_accept_only_one_baseline(self):
        first=self.save()
        def update(number):
            try:
                return self.save({**self.card,'summary':'并发研究版本'+str(number)},
                                 first['fingerprint'],'update-'+str(number))
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(update,[1,2]))
        self.assertEqual(sum(r is not None for r in results),1)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM source_versions').fetchone()[0],2)

if __name__=='__main__':unittest.main()

