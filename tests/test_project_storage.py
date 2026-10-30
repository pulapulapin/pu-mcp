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
            'workspaces': {'sample-story': {'path': str(self.storylab),
                                             'label': 'Synthetic story',
                                             'domain': 'writing'}},
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
        proposal = self.w.store.propose('sample-story', 'draft-one', 'Draft', 'Body', 0)
        self.w.store.commit_draft(proposal['id'], 'save-draft')
        planner = ProjectStorage(self.w)
        status = planner.get('sample-story')
        self.assertEqual(Path(status['project_root']), self.project_root.resolve())
        self.assertEqual(Path(status['proposed_store']),
                         self.project_root.resolve() / '.puknowledge/workspace.sqlite3')
        preview = planner.preview('sample-story')
        self.assertEqual(preview['state'], 'PREVIEW_READY')
        self.assertEqual(preview['project_dataset_ids'], ['project-model'])
        self.assertEqual(preview['project_knowledge_versions'], 3)
        self.assertEqual(preview['project_table_counts']['drafts'], 1)
        self.assertEqual(preview['project_table_counts']['draft_versions'], 1)
        self.assertFalse((self.project_root / '.puknowledge').exists())
        self.assertFalse(preview['writes_performed'])

    def test_existing_target_blocks_preview_without_overwrite(self):
        target = self.project_root / '.puknowledge'; target.mkdir()
        database = target / 'workspace.sqlite3'; database.write_bytes(b'existing')
        result = ProjectStorage(self.w).preview('sample-story')
        self.assertEqual(result['state'], 'BLOCKED')
        self.assertEqual(database.read_bytes(), b'existing')
        self.assertTrue(any(x['code'] == 'target_exists' for x in result['issues']))


if __name__ == '__main__':
    unittest.main()
