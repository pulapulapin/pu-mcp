"""Project-store migration planning uses synthetic data and never writes targets."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_api import workspace
from knowledge_data import Knowledge
from project_storage import ProjectStorage


class ProjectStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project_root = self.root / 'project'; self.storylab = self.project_root / '_storylab'
        self.storylab.mkdir(parents=True)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({
            'data_dir': str(self.root / 'shared'),
            'projects': {'sample-story': str(self.storylab)},
            'research_roots': [str(self.root)],
        }))
        env = patch.dict(os.environ, {
            'NOVEL_WORKBENCH_CONFIG': str(self.config),
            'PUKNOWLEDGE_CONFIG': str(self.config),
            'NOVEL_WORKBENCH_DATA': str(self.root / 'shared'),
        })
        env.start(); self.addCleanup(env.stop)
        self.w = workspace(); self.k = Knowledge(self.w)

    def save(self, kind, oid, body, dataset='project-model'):
        baseline = self.k.revision(dataset)
        args = dict(project='sample-story', kind=kind, dataset_id=dataset,
                    object_id=oid, body=body, baseline=baseline)
        preview = self.k.preview(**args)
        return self.k.save(**args, preview_fingerprint=preview['preview_fingerprint'],
                           operation_key=kind + '-' + oid)

    def test_status_and_preview_select_only_project_closure_without_writes(self):
        self.save('dataset', 'project-model', {
            'title': 'Synthetic private model', 'scope': 'project', 'purpose': 'model'})
        self.save('schema', 'note', {'fields': {'text': {'type': 'string'}},
                                     'allowed_relations': []})
        self.save('record', 'entry', {'record_type': 'note', 'schema_revision': 1,
                                      'values': {'text': 'candidate'},
                                      'status': 'candidate', 'evidence': []})
        self.save('dataset', 'global-reference', {
            'title': 'Synthetic global reference', 'scope': 'global', 'purpose': 'reference'},
                  dataset='global-reference')
        proposal = self.w.store.propose('sample-story', 'draft-one', 'Draft', 'Body', 0)
        self.w.store.commit_draft(proposal['id'], 'save-draft')
        with self.w.store.connection(write=True) as db:
            db.execute('INSERT INTO research_sources VALUES(?,?,?,?,?)',
                       ('shared-reference', 1, 'global', 'owner', 'url:synthetic'))
            db.execute('INSERT INTO research_source_versions VALUES(?,?,?,?)',
                       ('shared-reference', 1, '{"title":"Synthetic reference"}', 'now'))
            db.execute('INSERT INTO research_project_links VALUES(?,?,?,?,?)',
                       ('sample-story', 'shared-reference', 1, '{"active":true}', 'now'))
            db.execute('INSERT INTO research_annotation_versions VALUES(?,?,?,?,?,?,?)',
                       ('sample-story', 'note-one', 1, 'shared-reference', 1,
                        '{"quote":"evidence"}', 'now'))
        planner = ProjectStorage(self.w)
        status = planner.get('sample-story')
        self.assertEqual(Path(status['project_root']), self.project_root.resolve())
        self.assertEqual(Path(status['proposed_store']),
                         self.project_root.resolve() / '.puknowledge/workspace.sqlite3')
        preview = planner.preview('sample-story')
        self.assertEqual(preview['state'], 'PREVIEW_READY')
        self.assertEqual(preview['project_dataset_ids'], ['project-model'])
        self.assertEqual(preview['project_knowledge_versions'], 3)
        self.assertEqual(preview['global_dependency_dataset_ids'], ['global-reference'])
        self.assertEqual(preview['global_dependency_knowledge_versions'], 1)
        self.assertEqual(preview['project_table_counts']['drafts'], 1)
        self.assertEqual(preview['project_table_counts']['draft_versions'], 1)
        self.assertEqual(preview['dependency_research_source_ids'], ['shared-reference'])
        self.assertFalse((self.project_root / '.puknowledge').exists())
        self.assertFalse(preview['writes_performed'])

    def test_existing_target_blocks_preview_without_overwrite(self):
        target = self.project_root / '.puknowledge'; target.mkdir()
        database = target / 'workspace.sqlite3'; database.write_bytes(b'existing')
        result = ProjectStorage(self.w).preview('sample-story')
        self.assertEqual(result['state'], 'BLOCKED')
        self.assertEqual(database.read_bytes(), b'existing')
        self.assertTrue(any(x['code'] == 'target_exists' for x in result['issues']))

    def test_shadow_copy_requires_exact_preview_and_matches_source_without_routing_change(self):
        self.save('dataset', 'project-model', {
            'title': 'Synthetic private model', 'scope': 'project', 'purpose': 'model'})
        self.save('schema', 'note', {'fields': {'text': {'type': 'string'}},
                                     'allowed_relations': []})
        self.save('dataset', 'global-reference', {
            'title': 'Synthetic global reference', 'scope': 'global', 'purpose': 'reference'},
                  dataset='global-reference')
        proposal = self.w.store.propose('sample-story', 'draft-one', 'Draft', 'Body', 0)
        self.w.store.commit_draft(proposal['id'], 'save-draft')
        with self.w.store.connection(write=True) as db:
            db.execute('INSERT INTO research_sources VALUES(?,?,?,?,?)',
                       ('shared-reference', 1, 'global', 'owner', 'url:synthetic'))
            db.execute('INSERT INTO research_source_versions VALUES(?,?,?,?)',
                       ('shared-reference', 1, '{"title":"Synthetic reference"}', 'now'))
            db.execute('INSERT INTO research_project_links VALUES(?,?,?,?,?)',
                       ('sample-story', 'shared-reference', 1, '{"active":true}', 'now'))
            db.execute('INSERT INTO research_annotation_versions VALUES(?,?,?,?,?,?,?)',
                       ('sample-story', 'note-one', 1, 'shared-reference', 1,
                        '{"quote":"evidence"}', 'now'))
        planner = ProjectStorage(self.w)
        with self.assertRaisesRegex(ValueError, 'preview changed'):
            planner.shadow_copy('sample-story', '0' * 64)
        preview = planner.preview('sample-story')
        result = planner.shadow_copy('sample-story', preview['preview_fingerprint'])
        self.assertTrue(result['matches_source'])
        self.assertEqual(result['source_manifest']['dependency_source_ids'],
                         ['shared-reference'])
        self.assertFalse(result['routing_changed'])
        self.assertEqual(result['active_store'], str(self.w.store.path))
        self.assertTrue((self.project_root / '.puknowledge/workspace.sqlite3').exists())
        verified = planner.verify('sample-story')
        self.assertTrue(verified['matches_source'])
        self.assertEqual(verified['foreign_key_issues'], [])
        self.save('schema', 'global-note', {'fields': {'text': {'type': 'string'}},
                                            'allowed_relations': []},
                  dataset='global-reference')
        sync_preview = planner.sync_preview('sample-story')
        self.assertFalse(sync_preview['currently_matches_source'])
        synced = planner.sync('sample-story', sync_preview['preview_fingerprint'])
        self.assertTrue(synced['matches_source'])
        self.assertTrue(Path(synced['rollback_store']).is_file())
        self.assertTrue(planner.verify('sample-story')['matches_source'])


if __name__ == '__main__':
    unittest.main()
