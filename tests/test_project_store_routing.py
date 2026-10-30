"""Explicit active bindings route project-private calls without moving shared books."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_api import workspace
from knowledge_data import Knowledge
from longform_tools import _proposal_wb
from novel_workbench import Workbench
from project_storage import ProjectStorage


class ProjectStoreRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.storylab = self.root / 'story' / '_storylab'; self.storylab.mkdir(parents=True)
        self.config = self.root / 'config.json'
        self.env = patch.dict(os.environ, {
            'NOVEL_WORKBENCH_CONFIG': str(self.config),
            'PUKNOWLEDGE_CONFIG': str(self.config),
            'NOVEL_WORKBENCH_DATA': '',
        })
        self.env.start(); self.addCleanup(self.env.stop)

    def write(self, mode):
        self.config.write_text(json.dumps({
            'data_dir': str(self.root / 'central'),
            'books_root': str(self.root / 'books'),
            'projects': {'story': str(self.storylab)},
            'project_stores': {'story': {
                'path': str(self.root / 'story' / '.puknowledge'), 'mode': mode}},
        }))

    def test_active_routes_project_store_and_keeps_books_central(self):
        self.write('active')
        central = Workbench()
        project = Workbench(project_id='story')
        self.assertNotEqual(central.store.path, project.store.path)
        self.assertEqual(project.store_mode, 'project')
        self.assertEqual(project.books.store.path, central.store.path)
        central_proposal = central.store.propose('story', 'central-only', 'Central', 'old', 0)
        central.store.commit_draft(central_proposal['id'], 'central-save')
        project_proposal = project.propose('story', 'project-only', 'Project', 'new', 0)
        self.assertEqual([x['id'] for x in project.store.list_drafts('story')], [])
        preview = json.loads(_proposal_wb(
            lambda w: w.store.preview(project_proposal['id']), project_proposal['id']))
        self.assertTrue(preview['ok'], preview)
        project.store.commit_draft(project_proposal['id'], 'project-save')
        self.assertEqual([x['id'] for x in project.store.list_drafts('story')], ['project-only'])
        self.assertEqual([x['id'] for x in central.store.list_drafts('story')], ['central-only'])
        self.assertEqual(workspace('story').store.path, project.store.path)
        self.assertEqual(workspace().store.path, central.store.path)
        routed = Knowledge(workspace('story'))
        private = {'title': 'Private', 'scope': 'project', 'purpose': 'model'}
        preview = routed.preview('story', 'dataset', 'private-model', 'private-model', private, 0)
        routed.save('story', 'dataset', 'private-model', 'private-model', private, 0,
                    preview['preview_fingerprint'], 'private-save')
        self.assertEqual(routed.revision('private-model'), 1)
        with self.assertRaisesRegex(ValueError, '项目库不能创建'):
            routed.preview('story', 'dataset', 'global-model', 'global-model',
                           {'title': 'Global', 'scope': 'global', 'purpose': 'model'}, 0)
        storage = ProjectStorage(workspace())
        sync = storage.sync_preview('story')
        self.assertEqual(sync['state'], 'BLOCKED')
        self.assertTrue(any(x['code'] == 'active_full_sync_forbidden' for x in sync['issues']))

    def test_shadow_binding_keeps_runtime_on_shared_store(self):
        self.write('shadow')
        central = Workbench()
        project = Workbench(project_id='story')
        self.assertEqual(project.store.path, central.store.path)
        self.assertEqual(project.store_mode, 'shared')
        self.assertEqual(workspace('story').store.path, central.store.path)


if __name__ == '__main__':
    unittest.main()
