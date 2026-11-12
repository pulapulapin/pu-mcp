"""Prompt contracts against real, isolated knowledge storage."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from knowledge_api import execute, workspace
from knowledge_data import Knowledge


TEMPLATE_VALUES = {
    'prompt_id': 'novel-writer', 'name': '小说创作', 'role': '作者',
    'objective': '自然叙事', 'instructions': '人物行为自然。', 'avoid': '概念说明工具。',
    'output_preferences': '正文', 'discussion_preferences': '保留结论、依据和限制，删除重复。',
    'context_policy': '仅按任务读取需要的材料。', 'lifecycle': 'active',
    'version_label': 'v0.1', 'source': 'synthetic', 'change_note': 'initial',
}
CUSTOM_FIELDS = {
    'prompt_id': 'string', 'base_dataset_id': 'string', 'base_record_id': 'string',
    'base_revision': 'integer', 'base_fingerprint': 'string', 'instructions_add': 'string',
    'avoid_add': 'string', 'output_preferences_override': 'string',
    'discussion_preferences_add': 'string', 'context_policy_add': 'string',
    'lifecycle': 'string', 'source': 'string', 'change_note': 'string',
}


class PromptFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        projects = {}
        for name in ('owner', 'a', 'b'):
            path = self.root / name
            path.mkdir()
            (path / 'manuscript.txt').write_text('Synthetic manuscript unchanged.')
            projects[name] = {'path': str(path), 'label': name, 'domain': 'test'}
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'data_dir': str(self.root / 'data'), 'workspaces': projects}))
        env = patch.dict(os.environ, {'PUKNOWLEDGE_CONFIG': str(self.config),
                                     'NOVEL_WORKBENCH_CONFIG': str(self.config),
                                     'NOVEL_WORKBENCH_DATA': str(self.root / 'data')})
        env.start()
        self.addCleanup(env.stop)
        self.w = workspace()
        self.k = Knowledge(self.w)
        self.serial = 0
        self.create_dataset('owner', 'library', 'global')
        self.create_dataset('a', 'a-prompts', 'project')
        self.create_dataset('b', 'b-prompts', 'project')
        for project, dataset in (('owner', 'library'), ('a', 'a-prompts'), ('b', 'b-prompts')):
            self.save(project, 'schema', dataset, 'prompt_template', {
                'fields': {key: {'type': 'string'} for key in TEMPLATE_VALUES}})
            self.save(project, 'schema', dataset, 'prompt_customization', {
                'fields': {key: {'type': kind} for key, kind in CUSTOM_FIELDS.items()}})
        self.base = self.save('owner', 'record', 'library', 'novel-writer', self.template())

    def create_dataset(self, project, dataset, scope):
        return self.save(project, 'dataset', dataset, dataset,
                         {'title': dataset, 'scope': scope, 'purpose': 'model'})

    def args(self, project, kind, dataset, oid, body):
        return dict(project=project, kind=kind, dataset_id=dataset, object_id=oid,
                    body=body, baseline=self.k.revision(dataset))

    def save(self, project, kind, dataset, oid, body):
        args = self.args(project, kind, dataset, oid, body)
        p = self.k.preview(**args)
        self.serial += 1
        return self.k.save(**args, preview_fingerprint=p['preview_fingerprint'],
                           operation_key='write-' + str(self.serial))

    def template(self, **changes):
        return {'record_type': 'prompt_template', 'schema_revision': 1,
                'values': {**TEMPLATE_VALUES, **changes}}

    def customization(self, **changes):
        return {'record_type': 'prompt_customization', 'schema_revision': 1, 'values': {
            'prompt_id': 'novel-writer', 'base_dataset_id': 'library',
            'base_record_id': 'novel-writer', 'base_revision': self.base['revision'],
            'base_fingerprint': self.base['fingerprint'], 'instructions_add': '尊重力量边界。',
            'lifecycle': 'active', 'source': 'synthetic owner', 'change_note': 'adopt', **changes}}

    def resolve(self, **changes):
        return execute(self.w, 'prompt_resolve', {'project': 'a', 'prompt_id': 'novel-writer',
                       'customization_dataset_id': 'a-prompts', **changes})


class PromptValidationTests(PromptFixture):
    def test_invalid_base_is_rejected_before_any_record_write(self):
        for changes in ({'base_revision': 0}, {'base_revision': 999},
                        {'base_fingerprint': '0' * 64}, {'base_fingerprint': 'not-sha'},
                        {'prompt_id': 'different'}, {'base_record_id': 'missing'},
                        {'lifecycle': 'enabled'}):
            with self.subTest(changes=changes):
                args = self.args('a', 'record', 'a-prompts', 'novel-writer', self.customization(**changes))
                with self.assertRaises(ValueError):
                    self.k.preview(**args)

    def test_template_and_customization_scopes_cannot_be_reversed(self):
        with self.assertRaises(ValueError):
            self.save('a', 'record', 'a-prompts', 'novel-writer', self.template())
        with self.assertRaises(ValueError):
            self.save('owner', 'record', 'library', 'novel-writer', self.customization())

    def test_customization_cannot_inherit_private_records_or_other_customizations(self):
        custom = self.save('a', 'record', 'a-prompts', 'novel-writer', self.customization())
        body = self.customization(base_dataset_id='a-prompts', base_revision=custom['revision'],
                                  base_fingerprint=custom['fingerprint'])
        with self.assertRaises(ValueError):
            self.save('a', 'record', 'a-prompts', 'novel-writer', body)
        with self.assertRaises(ValueError):
            self.save('b', 'record', 'b-prompts', 'novel-writer', body)

    def test_import_cannot_bypass_reference_validation(self):
        result = self.k.import_preview(project='a', dataset_id='a-prompts',
            baseline=self.k.revision('a-prompts'), format='json', content=json.dumps([
                {'id': 'novel-writer', 'body': self.customization(base_fingerprint='0' * 64)}]))
        self.assertFalse(result['valid'])
        self.assertEqual(self.k.query('a', 'a-prompts')['total'], 0)

    def test_preview_is_rechecked_when_base_becomes_private(self):
        args = self.args('a', 'record', 'a-prompts', 'novel-writer', self.customization())
        p = self.k.preview(**args)
        self.save('owner', 'dataset', 'library', 'library',
                  {'title': 'private', 'scope': 'project', 'purpose': 'model'})
        with self.assertRaises(ValueError):
            self.k.save(**args, preview_fingerprint=p['preview_fingerprint'], operation_key='stale')

    def test_dataset_validation_reports_unavailable_prompt_dependencies(self):
        self.save('a', 'record', 'a-prompts', 'novel-writer', self.customization())
        self.save('owner', 'dataset', 'library', 'library',
                  {'title': 'private', 'scope': 'project', 'purpose': 'model'})
        report = self.k.validate('a', 'a-prompts')
        self.assertFalse(report['valid'])
        self.assertEqual(report['errors'][0]['id'], 'novel-writer')


class PromptResolverTests(PromptFixture):
    def setUp(self):
        super().setUp()
        self.custom = self.save('a', 'record', 'a-prompts', 'novel-writer', self.customization())

    def base_ref(self):
        return {'dataset_id': 'library', 'record_id': 'novel-writer',
                'revision': self.base['revision'], 'fingerprint': self.base['fingerprint']}

    def test_merge_has_sources_and_never_writes_database_or_manuscript(self):
        before = (self.root / 'data/workspace.sqlite3').read_bytes()
        result = self.resolve(turn_instruction='只讨论开篇，不写正文。')
        self.assertEqual(result['effective_config']['instructions'], '人物行为自然。\n\n尊重力量边界。')
        self.assertEqual(result['effective_config']['output_preferences'], '正文')
        self.assertEqual(result['effective_config']['turn_instruction'], '只讨论开篇，不写正文。')
        self.assertEqual([s['source'] for s in result['field_sources']['instructions']],
                         ['global_template', 'project_customization'])
        self.assertEqual(result['base_ref']['revision'], 1)
        self.assertEqual(result['customization_ref']['fingerprint'], self.custom['fingerprint'])
        self.assertFalse(result['canon'])
        self.assertEqual(before, (self.root / 'data/workspace.sqlite3').read_bytes())
        self.assertEqual((self.root / 'a/manuscript.txt').read_text(), 'Synthetic manuscript unchanged.')
        self.assertEqual(result['effective_fingerprint'], self.resolve(
            turn_instruction='只讨论开篇，不写正文。')['effective_fingerprint'])

    def test_global_upgrade_does_not_change_pinned_effective_configuration(self):
        old = self.resolve()
        updated = self.save('owner', 'record', 'library', 'novel-writer',
                            self.template(instructions='新版叙事要求。', version_label='v0.2'))
        current = self.resolve()
        self.assertEqual(current['effective_fingerprint'], old['effective_fingerprint'])
        self.assertEqual(current['effective_config'], old['effective_config'])
        self.assertIn('base_superseded', [w['code'] for w in current['warnings']])
        proposed = self.customization(base_revision=updated['revision'],
            base_fingerprint=updated['fingerprint'])['values']
        preview = self.resolve(customization_dataset_id='', proposed_customization=proposed)
        self.assertEqual(preview['effective_config']['instructions'], '新版叙事要求。\n\n尊重力量边界。')
        self.assertIsNone(preview['customization_ref'])
        self.assertTrue(preview['preview_only'])
        self.assertEqual(self.resolve()['effective_fingerprint'], old['effective_fingerprint'])

    def test_explicit_empty_output_override_differs_from_inherit(self):
        proposed = self.customization(output_preferences_override='')['values']
        result = self.resolve(customization_dataset_id='', proposed_customization=proposed)
        self.assertEqual(result['effective_config']['output_preferences'], '')
        self.assertEqual(result['field_sources']['output_preferences'][0]['source'], 'proposed_customization')
        self.assertEqual(self.resolve()['effective_config']['output_preferences'], '正文')

    def test_cross_project_scope_and_shared_base(self):
        self.save('b', 'record', 'b-prompts', 'novel-writer', self.customization(instructions_add='B要求。'))
        other = self.resolve(project='b', customization_dataset_id='b-prompts')
        self.assertEqual(other['effective_config']['instructions'], '人物行为自然。\n\nB要求。')
        self.assertEqual(other['base_ref'], self.resolve()['base_ref'])
        with self.assertRaises(ValueError):
            self.resolve(project='b')
        listed = execute(self.w, 'dataset_get', {'project': 'b'})
        self.assertNotIn('a-prompts', [d['dataset_id'] for d in listed['datasets']])

    def test_temporary_fixed_base_requires_no_persistent_adoption(self):
        result = self.resolve(project='b', customization_dataset_id='', base_ref=self.base_ref(),
                              turn_instruction='这次只列矛盾。')
        self.assertEqual(result['effective_config']['instructions'], '人物行为自然。')
        self.assertIsNone(result['customization_ref'])
        self.assertEqual(self.k.query('b', 'b-prompts')['total'], 0)

    def test_missing_ambiguous_or_malformed_sources_fail_without_fallback(self):
        cases = ({'customization_dataset_id': ''},
                 {'base_ref': self.base_ref()}, {'customization_revision': True},
                 {'customization_revision': -1}, {'customization_revision': 999},
                 {'customization_dataset_id': '', 'base_ref': {**self.base_ref(), 'revision': 0}},
                 {'customization_dataset_id': '', 'base_ref': {**self.base_ref(), 'fingerprint': '0' * 64}},
                 {'customization_dataset_id': '', 'proposed_customization': {}},
                 {'customization_dataset_id': '', 'customization_revision': 1, 'base_ref': self.base_ref()},
                 {'turn_instruction': 'x' * 10001}, {'project': 'unknown'})
        for case in cases:
            with self.subTest(case=list(case)):
                with self.assertRaises(ValueError):
                    self.resolve(**case)

    def test_archival_warns_but_latest_withdrawal_blocks_pinned_base(self):
        initial = self.resolve()
        self.save('owner', 'record', 'library', 'novel-writer', self.template(lifecycle='archived'))
        result = self.resolve()
        self.assertEqual(result['effective_fingerprint'], initial['effective_fingerprint'])
        self.assertIn('base_archived', [w['code'] for w in result['warnings']])
        body = self.template()
        body['status'] = 'withdrawn'
        self.save('owner', 'record', 'library', 'novel-writer', body)
        with self.assertRaises(ValueError):
            self.resolve()
        self.assertEqual(self.k.get('a', 'record', 'library', 'novel-writer', revision=1)['revision'], 1)

    def test_customization_history_and_rollback_are_explicit(self):
        self.save('a', 'record', 'a-prompts', 'novel-writer', self.customization(instructions_add='新项目要求。'))
        self.assertEqual(self.resolve()['effective_config']['instructions'], '人物行为自然。\n\n新项目要求。')
        old = self.resolve(customization_revision=1)
        self.assertEqual(old['effective_config']['instructions'], '人物行为自然。\n\n尊重力量边界。')
        self.save('a', 'record', 'a-prompts', 'novel-writer', self.customization())
        restored = self.resolve()
        self.assertEqual(restored['effective_config'], old['effective_config'])
        self.assertEqual(restored['customization_ref']['revision'], 3)

    def test_draft_base_or_customization_cannot_be_applied(self):
        draft = self.save('owner', 'record', 'library', 'novel-writer', self.template(lifecycle='draft'))
        with self.assertRaises(ValueError):
            self.resolve(customization_dataset_id='', base_ref={**self.base_ref(),
                'revision': draft['revision'], 'fingerprint': draft['fingerprint']})
        self.save('a', 'record', 'a-prompts', 'novel-writer', self.customization(lifecycle='draft'))
        with self.assertRaises(ValueError):
            self.resolve()


class PromptPackTests(PromptFixture):
    def test_pack_is_draft_and_only_explicit_activation_makes_modes_usable(self):
        pack = json.loads((ROOT / 'config/schemas/prompts-v0.2.json').read_text())
        self.create_dataset('owner', 'pack-library', 'global')
        for name, structure in pack['schemas'].items():
            self.save('owner', 'schema', 'pack-library', name, structure)
        args = {'project': 'owner', 'dataset_id': 'pack-library', 'format': 'json',
                'baseline': self.k.revision('pack-library'), 'content': json.dumps(pack['records'])}
        p = self.k.import_preview(**args)
        self.assertTrue(p['valid'], p['errors'])
        self.k.import_commit(**args, preview_fingerprint=p['preview_fingerprint'], operation_key='pack')
        active = self.k.query('a', 'pack-library', filters=[{'field': 'lifecycle', 'op': 'eq', 'value': 'active'}])
        self.assertEqual(active['total'], 0)
        expected_names = {'creative-explorer': '创意破局', 'story-director': '故事导演',
                          'novel-writer': '小说创作', 'serial-editor': '连载编辑',
                          'reader-reviewer': '普通读者'}
        self.assertEqual({r['id'] for r in pack['records']}, set(expected_names))
        for record in pack['records']:
            mode = record['id']
            old = self.k.get('a', 'record', 'pack-library', mode)
            with self.assertRaises(ValueError):
                execute(self.w, 'prompt_resolve', {'project': 'a', 'prompt_id': mode, 'base_ref': {
                    'dataset_id': 'pack-library', 'record_id': mode, 'revision': 1, 'fingerprint': old['fingerprint']}})
            body = copy.deepcopy(record['body'])
            body['values']['lifecycle'] = 'active'
            saved = self.save('owner', 'record', 'pack-library', mode, body)
            result = execute(self.w, 'prompt_resolve', {'project': 'a', 'prompt_id': mode, 'base_ref': {
                'dataset_id': 'pack-library', 'record_id': mode, 'revision': saved['revision'],
                'fingerprint': saved['fingerprint']}})
            self.assertEqual(result['effective_config']['name'], expected_names[mode])


if __name__ == '__main__':
    unittest.main()
