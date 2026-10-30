"""Synthetic story graph; no project manuscripts or runtime configuration."""
import json
import unittest
from pathlib import Path
from tests import test_knowledge_data as fixtures
from story_planning import StoryPlanning, SCHEMA


class StoryPlanningTests(unittest.TestCase):
    setUp = fixtures.KnowledgeTests.setUp
    save = fixtures.KnowledgeTests.save

    def setup_plan(self):
        self.save('dataset', 'plan', {'title': 'Synthetic plan', 'scope': 'project', 'purpose': 'model'}, dataset='plan')
        self.save('schema', 'story_node', SCHEMA, dataset='plan')
        self.plan = StoryPlanning(self.w)

    def commit(self, changes, key='graph'):
        baseline = self.k.revision('plan')
        p = self.plan.preview('owner', 'plan', baseline, changes)
        return self.plan.save('owner', 'plan', baseline, changes, p['preview_fingerprint'], key)

    def node(self, oid, kind='event'):
        return {'id': oid, 'values': {'kind': kind, 'title': oid, 'summary': 'Synthetic candidate'}}

    def edge(self, oid, a, b, kind='depends_on'):
        return {'id': oid, 'relation_type': kind, 'from_id': a, 'to_id': b}

    def test_preview_atomic_save_and_replay(self):
        self.setup_plan()
        changes = {'nodes': [self.node('a'), self.node('b')], 'edges': [self.edge('a-b', 'b', 'a')]}
        baseline = self.k.revision('plan')
        before = self.k.query('owner', 'plan')['total']
        p = self.plan.preview('owner', 'plan', baseline, changes)
        self.assertEqual(self.k.query('owner', 'plan')['total'], before)
        result = self.plan.save('owner', 'plan', baseline, changes, p['preview_fingerprint'], 'save')
        self.assertEqual(self.plan.save('owner', 'plan', baseline, changes, p['preview_fingerprint'], 'save'), result)
        rows = self.plan.get('owner', 'plan')
        self.assertEqual(len(rows['nodes']), 2)
        self.assertEqual(len(rows['edges']), 1)
        self.assertTrue(all(n['canon'] is False for n in rows['nodes']))
        self.assertEqual(len({n['dataset_revision'] for n in rows['nodes'] + rows['edges']}), 1)
        with self.assertRaises(ValueError):
            self.plan.save('owner', 'plan', baseline, changes, p['preview_fingerprint'], 'different')

    def test_48_chapters_impact_paths_and_history(self):
        self.setup_plan()
        nodes = [self.node('v', 'volume')] + [self.node('c'+str(i), 'chapter') for i in range(1, 49)]
        nodes += [self.node('e27'), self.node('e29')]
        edges = [self.edge('v-c'+str(i), 'v', 'c'+str(i), 'contains') for i in range(1, 49)]
        edges += [self.edge('c27-e', 'c27', 'e27', 'contains'), self.edge('c29-e', 'c29', 'e29', 'contains'), self.edge('causal', 'e29', 'e27')]
        first = self.commit({'nodes': nodes, 'edges': edges})
        old = self.plan.get('owner', 'plan', dataset_revision=first['dataset_revision'])
        change = self.node('e27'); change['values']['summary'] = 'Cooperation changes'
        p = self.plan.preview('owner', 'plan', self.k.revision('plan'), {'nodes': [change]})
        self.assertIn('c29', p['impact']['chapter_ids'])
        self.assertTrue(any('causal' in x['relation_ids'] for x in p['impact']['paths']))
        self.commit({'nodes': [change]}, 'update')
        latest = self.plan.get('owner', 'plan')
        self.assertTrue(latest['stale_endpoints'])
        exact = self.plan.get('owner', 'plan', dataset_revision=first['dataset_revision'])
        self.assertEqual(exact, old)
        self.assertFalse(exact['stale_endpoints'])

    def test_bad_endpoint_cycle_and_cross_project_rejected(self):
        self.setup_plan()
        bad = {'nodes': [self.node('a')], 'edges': [self.edge('bad', 'a', 'missing')]}
        with self.assertRaises(ValueError): self.commit(bad)
        self.assertEqual(self.k.query('owner', 'plan')['total'], 0)
        cyclic = {'nodes': [self.node('a', 'unit'), self.node('b', 'unit')], 'edges': [self.edge('ab', 'a', 'b', 'contains'), self.edge('ba', 'b', 'a', 'contains')]}
        with self.assertRaises(ValueError): self.commit(cyclic)
        with self.assertRaises(ValueError): self.plan.get('other', 'plan')
        with self.assertRaises(ValueError): self.plan.preview('other', 'plan', 2, {'nodes': [self.node('a')]})

    def test_candidate_only_pagination_and_withdrawal(self):
        self.setup_plan()
        bad = self.node('a'); bad['values']['story_state'] = 'adopted_plan'
        with self.assertRaises(ValueError): self.commit({'nodes': [bad]})
        self.commit({'nodes': [self.node('a'), self.node('b')]})
        page = self.plan.get('owner', 'plan', limit=1)
        self.assertEqual(page['next_offset'], 1)
        second = self.plan.get('owner', 'plan', dataset_revision=page['dataset_revision'], offset=1, limit=1)
        self.assertNotEqual(page['nodes'][0]['object_id'], second['nodes'][0]['object_id'])
        withdrawn = self.node('a'); withdrawn['status'] = 'withdrawn'
        self.commit({'nodes': [withdrawn]}, 'withdraw')
        self.assertEqual([n['object_id'] for n in self.plan.get('owner', 'plan')['nodes']], ['b'])
        with self.assertRaises(ValueError): self.plan.get('owner', 'plan', dataset_revision=999)

    def test_invalid_batch_does_not_leave_valid_prefix(self):
        self.setup_plan()
        baseline = self.k.revision('plan')
        bad = {'nodes': [self.node('a')], 'edges': [self.edge('bad', 'a', 'missing')]}
        from story_planning import normalize
        from novel_store import digest
        from novel_evidence import encode
        fp = digest(encode({'project': 'owner', 'dataset_id': 'plan', 'baseline': baseline, 'change_set': normalize(bad)}))
        with self.assertRaises(ValueError): self.plan.save('owner', 'plan', baseline, bad, fp, 'bad')
        self.assertEqual(self.k.revision('plan'), baseline)
        self.assertEqual(self.k.query('owner', 'plan')['total'], 0)

    def test_public_dataset_and_tampered_preview_rejected(self):
        self.setup_plan()
        changes = {'nodes': [self.node('a')]}
        with self.assertRaises(ValueError): self.plan.save('owner', 'plan', 2, changes, '0'*64, 'tamper')
        self.save('dataset', 'shared', {'title': 'Synthetic shared', 'scope': 'global', 'purpose': 'model'}, dataset='shared')
        with self.assertRaises(ValueError): self.plan.get('owner', 'shared')

    def test_removed_dependency_and_explicit_rebind(self):
        self.setup_plan()
        self.commit({'nodes': [self.node('a'), self.node('b')], 'edges': [self.edge('ab', 'b', 'a')]})
        removal = self.edge('ab', 'b', 'a'); removal['status'] = 'withdrawn'
        p = self.plan.preview('owner', 'plan', self.k.revision('plan'), {'edges': [removal]})
        self.assertTrue(any(x['graph'] == 'before' and x['target_id'] == 'b' for x in p['impact']['paths']))
        changed = self.node('a'); changed['values']['summary'] = 'Revised candidate'
        self.commit({'nodes': [changed], 'edges': [self.edge('ab', 'b', 'a')]}, 'rebind')
        self.assertFalse(self.plan.get('owner', 'plan')['stale_endpoints'])

    def test_real_stdio_discovery_preview_save_and_read(self):
        import asyncio
        import os
        import sys
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        self.setup_plan()
        async def run():
            params = StdioServerParameters(command=sys.executable,
                args=['-B', str(Path(__file__).resolve().parents[1] / 'scripts/knowledge_entry.py'),
                      '--config', str(self.config), '--modules', 'core,longform'],
                cwd=str(self.root), env=dict(os.environ))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = {t.name: t for t in (await session.list_tools()).tools}
                    self.assertTrue({'story_plan_get', 'story_plan_preview', 'story_plan_save'} <= set(tools))
                    self.assertTrue(tools['story_plan_get'].annotations.read_only_hint)
                    async def call(name, args):
                        r = await session.call_tool(name, args)
                        self.assertFalse(r.is_error)
                        data = json.loads(r.content[0].text)
                        self.assertTrue(data['ok'], data)
                        return data['result']
                    args = {'project': 'owner', 'dataset_id': 'plan', 'baseline': 2,
                            'change_set': {'nodes': [self.node('a')]}}
                    p = await call('story_plan_preview', args)
                    result = await call('story_plan_save', {**args, 'preview_fingerprint': p['preview_fingerprint'], 'operation_key': 'stdio'})
                    graph = await call('story_plan_get', {'project': 'owner', 'dataset_id': 'plan', 'dataset_revision': result['dataset_revision']})
                    self.assertEqual(graph['nodes'][0]['object_id'], 'a')
        asyncio.run(run())

    def test_node_and_edge_can_be_withdrawn_atomically(self):
        self.setup_plan()
        self.commit({'nodes': [self.node('a'), self.node('b')], 'edges': [self.edge('ab', 'b', 'a')]})
        node = self.node('a'); node['status'] = 'withdrawn'
        edge = self.edge('ab', 'b', 'a'); edge['status'] = 'withdrawn'
        self.commit({'nodes': [node], 'edges': [edge]}, 'remove')
        graph = self.plan.get('owner', 'plan')
        self.assertFalse(graph['edges'])
        self.assertFalse(graph['stale_endpoints'])
        self.assertEqual([n['object_id'] for n in graph['nodes']], ['b'])
