"""Recovery of real external files, never tests against the author's fiction."""
import asyncio
import copy
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
try:
    from tests.test_prompt_library import PromptFixture
except ImportError:
    from test_prompt_library import PromptFixture
try:
    from tests.support import create_story
except ImportError:
    from support import create_story
from novel_workbench import Workbench
from longform_tools import register_longform
class ToolRegistry:
    def __init__(self): self.tools = {}
    def tool(self, **options):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register
    async def call_tool(self, name, args):
        return self.tools[name](**args)


class RecoveryTests(PromptFixture):
    def setUp(self):
        super().setUp()
        cfg = json.loads(self.config.read_text())
        cfg['workspaces'].pop('a')
        cfg['projects'] = {'a': str(create_story(self.root / 'a'))}
        self.source = self.root / 'a' / 'canon.md'
        self.source.write_text('# Frozen\nA fixed fact.\n# Candidate\nNot approved.')
        self.manuscript = self.root / 'a' / 'chapter.md'
        self.manuscript.write_text('A working chapter, not approved.')
        cfg['fs_workspaces'] = {'a': {'path': str(self.root / 'a')}}
        self.config.write_text(json.dumps(cfg))
        self.w = Workbench()
        self.save('a', 'record', 'a-prompts', 'novel-writer', self.customization())
        snap = {'task': 'New story direction', 'summary': 'Selected direction',
                'next_step': 'Design candidate events', 'decisions': ['No approved new plot'],
                'task_context': {'task_id': 'task-new', 'state': 'active',
                                 'direction_revision': 2, 'stage': 'story_design'}}
        p = self.w.conversations.preview('a', 'current', snap)
        self.w.conversations.save('a', 'current', snap, 0, p['preview_fingerprint'], 'snapshot')
        self.w.save_checkpoint('a', 'Obsolete pause', 'Old instruction', 'Do old research', [], 0)
        self.binding = {'prompt_dataset_id': 'a-prompts', 'prompt_ids': ['novel-writer'],
                        'documents': [self.doc('canon', self.source, 'mixed_status_document'),
                                      self.doc('chapter', self.manuscript, 'working_manuscript')],
                        'records': []}

    def doc(self, sid, path, authority):
        return {'id': sid, 'path': path.name, 'fingerprint': hashlib.sha256(path.read_bytes()).hexdigest(),
                'authority': authority, 'required': True}

    def task_refs(self, refs):
        snap = {'task': 'New story direction', 'summary': 'Selected direction',
                'next_step': 'Design candidate events', 'decisions': ['No approved new plot'],
                'task_context': {'task_id': 'task-new', 'state': 'active',
                                 'direction_revision': 2, 'stage': 'story_design'}, 'references': refs}
        p = self.w.conversations.preview('a', 'current', snap)
        self.w.conversations.save('a', 'current', snap, 1, p['preview_fingerprint'], 'task-refs')

    def work_reference(self, text):
        if not self.k.query('a', 'a-prompts', record_type='work_reference')['total']:
            self.save('a', 'schema', 'a-prompts', 'work_reference', {'fields': {'text': {'type': 'string'}}})
        row = self.save('a', 'record', 'a-prompts', 'rules',
                        {'record_type': 'work_reference', 'schema_revision': 1, 'values': {'text': text}})
        return {'kind': 'project_record', 'dataset_id': 'a-prompts', 'object_id': 'rules',
                'revision': row['revision'], 'fingerprint': row['fingerprint']}

    def call(self, **kwargs):
        from writing_context import recover
        settings = copy.deepcopy(self.w.settings)
        settings['writing_contexts'] = {'a': copy.deepcopy(self.binding)}
        self.w.settings = settings
        return recover(self.w, 'a', **kwargs)

    def test_creative_contract_is_delivered_but_blind_review_has_no_author_workflow(self):
        normal = self.call()
        contract = normal['creative_workflow']
        self.assertEqual(contract['kind'], 'evidence_to_revision')
        self.assertFalse(contract['automatic_analysis'])
        self.assertIn('source_version', contract['review_fields'])
        self.assertEqual(contract['task_boundary']['task_id'], normal['task']['task_id'])
        self.assertEqual(contract['task_boundary']['next_step'], normal['task']['next_step'])
        blind = self.call(prompt_id='reader-reviewer')['creative_workflow']
        self.assertEqual(blind['kind'], 'independent_reading')
        self.assertNotIn('steps', blind)
        self.assertNotIn('review_fields', blind)
        self.assertNotIn('task_boundary', blind)

    def test_existing_tool_recovers_external_files_not_empty_json(self):
        cfg = json.loads(self.config.read_text())
        cfg['writing_contexts'] = {'a': self.binding}
        self.config.write_text(json.dumps(cfg))
        async def run():
            server = ToolRegistry()
            register_longform(server)
            blocks = await server.call_tool('writing_get_context', {'project': 'a'})
            result = json.loads(blocks)
            self.assertEqual(result['recovery']['state'], 'READY')
            self.assertIn('A fixed fact.', result['recovery']['documents'][0]['text'])
            self.assertEqual(result['next_task']['instruction'], 'New story direction')
            self.assertNotIn('Obsolete pause', json.dumps(result))
        asyncio.run(run())

    def test_stale_required_file_blocks_without_delivering_wrong_revision(self):
        self.source.write_text('Unexpected update')
        r = self.call()
        self.assertEqual(r['state'], 'BLOCKED')
        self.assertNotIn('Unexpected update', json.dumps(r))
        self.assertTrue(r['issues'])

    def test_optional_missing_source_and_budget_are_partial(self):
        self.binding['documents'][0]['required'] = False
        self.source.unlink()
        self.assertEqual(self.call()['state'], 'PARTIAL')
        self.binding['documents'] = [self.binding['documents'][1]]
        r = self.call(max_chars=1)
        self.assertEqual(r['state'], 'PARTIAL')
        self.assertFalse(r['delivery_complete'])

    def test_full_recovery_preserves_mixed_status_and_does_not_write(self):
        before = self.source.read_bytes()
        with self.w.store.connection() as db:
            rows = db.execute('SELECT count(*) FROM knowledge_versions').fetchone()[0]
        r = self.call(prompt_id='novel-writer')
        self.assertEqual(r['state'], 'READY')
        self.assertFalse(r['behavior_verified'])
        self.assertEqual(r['documents'][0]['authority'], 'mixed_status_document')
        self.assertIn('# Candidate', r['documents'][0]['text'])
        self.assertEqual(r['prompts'][0]['base_ref']['revision'], 1)
        self.assertEqual(r['task']['direction_revision'], 2)
        self.assertEqual(self.source.read_bytes(), before)
        with self.w.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM knowledge_versions').fetchone()[0], rows)

    def test_foreign_private_record_blocks_without_leaking(self):
        self.binding['records'] = [{'id': 'private', 'dataset_id': 'b-prompts',
                                   'record_id': 'anything', 'revision': 1, 'fingerprint': '0'*64,
                                   'authority': 'working_reference', 'required': True}]
        r = self.call()
        self.assertEqual(r['state'], 'BLOCKED')
        self.assertNotIn('body', r['records'])

    def test_mode_exclusions_prevent_author_material_in_independent_review(self):
        self.binding['documents'][0]['exclude_modes'] = ['novel-writer']
        r = self.call(prompt_id='novel-writer')
        self.assertEqual([x['id'] for x in r['documents']], ['chapter'])

    def test_unknown_mode_cannot_claim_ready(self):
        self.assertEqual(self.call(prompt_id='missing')['state'], 'BLOCKED')

    def test_selected_sources_defer_unread_material_without_claiming_full_context(self):
        self.source.write_text('Changed and not selected')
        r = self.call(prompt_id='novel-writer', source_ids=['chapter'])
        self.assertEqual(r['state'], 'READY')
        self.assertEqual([x['id'] for x in r['documents']], ['chapter'])
        self.assertEqual(r['recovery_scope']['deferred_ids'], ['canon'])
        self.assertFalse(r['recovery_scope']['full_project_verified'])
        self.assertEqual(r['source_catalog'][0]['fingerprint'], self.binding['documents'][0]['fingerprint'])
        self.assertFalse(r['source_catalog'][0]['selected'])
        self.assertEqual(self.call(source_ids=['canon'])['state'], 'BLOCKED')

    def test_selected_sources_cannot_skip_task_pins_or_request_unavailable_ids(self):
        ref = self.work_reference('Mandatory task rule')
        self.task_refs([ref])
        r = self.call(source_ids=['chapter'])
        self.assertEqual(len(r['records']), 1)
        self.assertEqual(r['records'][0]['binding_source'], 'task_snapshot')
        self.binding['documents'][0]['exclude_modes'] = ['novel-writer']
        for ids in ([], ['chapter', 'chapter'], ['foreign'], ['canon']):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.call(prompt_id='novel-writer', source_ids=ids)

    def test_blind_selected_catalog_cannot_disclose_author_sources(self):
        self.save('owner', 'record', 'library', 'reader-reviewer', self.template(prompt_id='reader-reviewer'))
        base = self.k.get('a', 'record', 'library', 'reader-reviewer')
        self.save('a', 'record', 'a-prompts', 'reader-reviewer', self.customization(
            prompt_id='reader-reviewer', base_record_id='reader-reviewer',
            base_revision=base['revision'], base_fingerprint=base['fingerprint']))
        self.binding['prompt_ids'].append('reader-reviewer')
        r = self.call(prompt_id='reader-reviewer', source_ids=['chapter'])
        self.assertEqual([x['id'] for x in r['source_catalog']], ['chapter'])
        self.assertEqual(r['records'], [])
        self.assertNotIn('task_boundary', r['creative_workflow'])
        with self.assertRaises(ValueError):
            self.call(prompt_id='reader-reviewer', source_ids=['canon'])

    def test_manuscript_range_delivers_only_pinned_unicode_excerpt(self):
        self.manuscript.write_text('🙂第一章\n选中正文\n第二章秘密')
        self.binding['documents'][1] = self.doc('chapter', self.manuscript, 'working_manuscript')
        fp = self.binding['documents'][1]['fingerprint']
        part = dict(source_id='chapter', expected_fingerprint=fp, start_char=5, end_char=9)
        r = self.call(source_ids=['chapter'], document_ranges=[part])
        self.assertEqual(r['state'], 'READY')
        document = r['documents'][0]
        self.assertEqual(document['text'], '选中正文')
        self.assertEqual(document['excerpt']['start_line'], 2)
        self.assertFalse(document['excerpt']['whole_document_delivered'])
        self.assertEqual(document['excerpt']['text_fingerprint'], hashlib.sha256('选中正文'.encode()).hexdigest())
        self.assertNotIn('第二章秘密', json.dumps(r, ensure_ascii=False))
        self.manuscript.write_text('Changed')
        self.assertEqual(self.call(source_ids=['chapter'], document_ranges=[part])['state'], 'BLOCKED')

    def test_source_map_only_indexes_selected_material_and_respects_budget(self):
        self.manuscript.write_text('# 第一章｜测试\n正文')
        self.binding['documents'][1] = self.doc('chapter', self.manuscript, 'working_manuscript')
        r = self.call(source_ids=['chapter'], include_source_map=True)
        self.assertEqual(r['source_map']['observed_chapter_headings'], 1)
        self.assertEqual([x['source_id'] for x in r['source_map']['sources']], ['chapter'])
        self.assertFalse(r['source_map']['saved'])
        small = self.call(source_ids=['chapter'], include_source_map=True, max_chars=100)
        self.assertTrue(small['source_map']['content_omitted'])
        self.assertEqual(small['state'], 'PARTIAL')

    def test_source_fact_proposals_do_not_fetch_unselected_documents(self):
        self.manuscript.write_text('男性。')
        self.binding['documents'][1] = self.doc('chapter', self.manuscript, 'working_manuscript')
        proposal = dict(id='gender', source_id='chapter',
            expected_fingerprint=self.binding['documents'][1]['fingerprint'],
            kind='character', entity_id='protagonist', field='gender', value='男性', quote='男性。')
        r = self.call(source_ids=['chapter'], source_facts=[proposal])
        self.assertEqual(r['source_map']['fact_candidates'][0]['evidence_state'], 'anchored')
        self.assertFalse(r['source_map']['saved'])
        with self.assertRaises(ValueError):
            self.call(source_ids=['canon'], source_facts=[proposal])

    def test_manuscript_range_cannot_hide_rules_or_use_unknown_or_empty_ranges(self):
        fp = self.binding['documents'][1]['fingerprint']
        part = dict(source_id='chapter', expected_fingerprint=fp, start_char=0, end_char=4)
        for ids, parts in [(None, [part]), (['chapter'], []), (['chapter'], [part, part]),
                (['canon'], [{**part, 'source_id': 'canon'}]),
                (['chapter'], [{**part, 'end_char': 0}])]:
            with self.subTest(ids=ids, parts=parts), self.assertRaises(ValueError):
                self.call(source_ids=ids, document_ranges=parts)
        for parts in [[{**part, 'expected_fingerprint': '0'*64}], [{**part, 'end_char': 9999}]]:
            self.assertEqual(self.call(source_ids=['chapter'], document_ranges=parts)['state'], 'BLOCKED')

    def test_current_task_loads_new_reference_and_replaces_old_binding(self):
        old = self.work_reference('Old rule')
        self.binding['records'] = [{'id': 'rules', 'dataset_id': old['dataset_id'],
                                   'record_id': old['object_id'], 'revision': old['revision'],
                                   'fingerprint': old['fingerprint'], 'authority': 'working_reference'}]
        new = self.work_reference('New rule explicitly selected by current task')
        self.task_refs([new])
        r = self.call()
        self.assertEqual(r['state'], 'READY')
        self.assertEqual(len(r['records']), 1)
        self.assertEqual(r['records'][0]['record']['revision'], 2)
        self.assertEqual(r['records'][0]['record']['body']['values']['text'], 'New rule explicitly selected by current task')
        self.assertEqual(r['records'][0]['binding_source'], 'task_snapshot')
        self.assertEqual(r['records'][0]['supersedes_manifest']['revision'], 1)

    def test_task_reference_missing_from_manifest_is_read_at_exact_version(self):
        ref = self.work_reference('Pinned task rule')
        self.work_reference('Later version must not be silently used')
        self.task_refs([ref])
        r = self.call()
        self.assertEqual(r['state'], 'READY')
        self.assertEqual(r['records'][0]['record']['body']['values']['text'], 'Pinned task rule')
        self.assertTrue(r['records'][0]['newer_revision_available'])
        self.assertFalse(r['records'][0]['record']['canon'])

    def test_task_reference_cannot_cross_project_or_guess_missing_version(self):
        for ref in [dict(kind='project_record', dataset_id='b-prompts', object_id='secret', revision=1, fingerprint='0'*64),
                    dict(kind='project_record', dataset_id='a-prompts', object_id='novel-writer', fingerprint='0'*64)]:
            with self.subTest(ref=ref):
                # Use a new snapshot operation for each case without touching its task direction.
                snap = {'task':'New story direction','summary':'Selected direction','next_step':'Design',
                        'task_context':{'task_id':'task-new','state':'active','direction_revision':2,'stage':'story_design'},
                        'references':[ref]}
                current = self.w.conversations.resolve('a')['backup']['revision']
                p = self.w.conversations.preview('a','current',snap)
                self.w.conversations.save('a','current',snap,current,p['preview_fingerprint'],'ref-'+str(current))
                self.assertEqual(self.call()['state'], 'BLOCKED')

    def test_conflicting_pins_in_one_task_are_not_silently_overwritten(self):
        one = self.work_reference('First rule')
        two = self.work_reference('Second rule')
        self.task_refs([one, two])
        self.assertEqual(self.call()['state'], 'BLOCKED')

    def test_duplicate_manifest_endpoints_do_not_silently_lose_a_source(self):
        ref = self.work_reference('Rule')
        one = {'id':'first','dataset_id':ref['dataset_id'],'record_id':ref['object_id'],
               'revision':ref['revision'],'fingerprint':ref['fingerprint'],'authority':'working_reference'}
        self.binding['records'] = [one, {**one, 'id':'second'}]
        from writing_context import Binding
        with self.assertRaises(ValueError):
            Binding.model_validate(self.binding)

    def test_task_pin_excluded_by_selected_mode_cannot_claim_complete(self):
        ref = self.work_reference('Restricted working text')
        self.binding['records'] = [{'id':'rules','dataset_id':ref['dataset_id'],
                                   'record_id':ref['object_id'],'revision':ref['revision'],
                                   'fingerprint':ref['fingerprint'],'authority':'working_reference',
                                   'exclude_modes':['novel-writer']}]
        self.task_refs([ref])
        r = self.call(prompt_id='novel-writer')
        self.assertEqual(r['state'], 'BLOCKED')
        self.assertEqual(r['records'], [])

    def test_record_sources_are_exact_and_withdrawal_blocks(self):
        ref = self.k.get('a', 'record', 'a-prompts', 'novel-writer')
        # A reference can contain working guidance without becoming Canon.
        self.binding['records'] = [{'id': 'working', 'dataset_id': 'a-prompts',
                                   'record_id': 'novel-writer', 'revision': ref['revision'],
                                   'fingerprint': ref['fingerprint'],
                                   'authority': 'working_reference'}]
        r = self.call()
        self.assertEqual(r['state'], 'READY')
        self.assertFalse(r['records'][0]['record']['canon'])
        body = self.customization(); body['status'] = 'withdrawn'
        self.save('a', 'record', 'a-prompts', 'novel-writer', body)
        self.assertEqual(self.call()['state'], 'BLOCKED')

    def test_missing_task_blocks_even_when_sources_are_available(self):
        with self.w.store.connection(write=True) as db:
            db.execute('DELETE FROM session_backup_versions')
            db.execute('DELETE FROM checkpoints')
        self.assertEqual(self.call()['state'], 'BLOCKED')

    def test_checkpoint_only_does_not_certify_current_direction(self):
        with self.w.store.connection(write=True) as db:
            db.execute('DELETE FROM session_backup_versions')
        self.assertEqual(self.call()['state'], 'BLOCKED')

    def test_wrong_record_fingerprint_blocks(self):
        self.binding['records'] = [{'id': 'rules', 'dataset_id': 'a-prompts',
                                   'record_id': 'novel-writer', 'revision': 1, 'fingerprint': '0'*64,
                                   'authority': 'working_reference'}]
        self.assertEqual(self.call()['state'], 'BLOCKED')

    def test_document_change_during_recovery_is_not_ready(self):
        from workspace_fs import FsWorkspace
        original = FsWorkspace.open_file
        count = 0
        def changing(fs, path):
            nonlocal count
            result = original(fs, path)
            count += 1
            if count == 1:
                self.source.write_text('Changed during read')
            return result
        with patch.object(FsWorkspace, 'open_file', changing):
            self.assertEqual(self.call()['state'], 'BLOCKED')

    def test_invalid_manifest_cannot_expand_filesystem_access(self):
        cfg = json.loads(self.config.read_text())
        self.binding['documents'][0]['path'] = '../outside.md'
        cfg['writing_contexts'] = {'a': self.binding}
        self.config.write_text(json.dumps(cfg))
        with self.assertRaises(ValueError):
            Workbench()

    def test_reader_receives_no_author_task_or_reference_intent(self):
        self.save('owner', 'record', 'library', 'reader-reviewer',
                  self.template(prompt_id='reader-reviewer'))
        base = self.k.get('a', 'record', 'library', 'reader-reviewer')
        self.save('a', 'record', 'a-prompts', 'reader-reviewer', self.customization(
            prompt_id='reader-reviewer', base_record_id='reader-reviewer',
            base_fingerprint=base['fingerprint']))
        self.binding['prompt_ids'].append('reader-reviewer')
        self.task_refs([{'kind':'project_record','dataset_id':'b-prompts','object_id':'secret',
                         'revision':1,'fingerprint':'0'*64}])
        r = self.call(prompt_id='reader-reviewer')
        self.assertEqual(r['state'], 'READY')
        self.assertEqual([x['id'] for x in r['documents']], ['chapter'])
        self.assertNotIn('No approved new plot', json.dumps(r))
        self.assertNotIn('New story direction', json.dumps(r))

    def test_validation_remains_structural_failure_with_explicit_scope(self):
        async def run():
            server = ToolRegistry(); register_longform(server)
            blocks = await server.call_tool('writing_validate', {'project': 'a'})
            result = json.loads(blocks)
            self.assertFalse(result['valid'])
            self.assertEqual(result['validation_scope'], 'storylab_json_structure')
            self.assertFalse(result['external_documents_validated'])
        asyncio.run(run())

    def test_unconfigured_reader_tool_does_not_return_author_intent(self):
        server = ToolRegistry(); register_longform(server)
        result = json.loads(asyncio.run(server.call_tool(
            'writing_get_context', {'project': 'a', 'prompt_id': 'reader-reviewer'})))
        self.assertEqual(result['recovery']['state'], 'PARTIAL')
        self.assertNotIn('New story direction', json.dumps(result))
        self.assertNotIn('No approved new plot', json.dumps(result))

    def test_tool_budget_includes_legacy_context_envelope(self):
        cfg = json.loads(self.config.read_text()); cfg['writing_contexts'] = {'a': self.binding}
        self.config.write_text(json.dumps(cfg))
        contract = self.root / 'a' / 'story-contract.json'
        body = json.loads(contract.read_text()); body['logline'] = 'x'*30000
        contract.write_text(json.dumps(body))
        server = ToolRegistry(); register_longform(server)
        result = json.loads(asyncio.run(server.call_tool(
            'writing_get_context', {'project': 'a', 'max_chars': 20000})))
        self.assertNotEqual(result['recovery']['state'], 'READY')
        self.assertFalse(result['recovery']['delivery_complete'])
