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

    def test_distributed_schema_matches_runtime_contract(self):
        pack = json.loads((Path(__file__).resolve().parents[1] /
                           'config/schemas/story-planning.json').read_text())
        self.assertEqual(pack['schema'], SCHEMA)

    def commit(self, changes, key='graph'):
        baseline = self.k.revision('plan')
        p = self.plan.preview('owner', 'plan', baseline, changes)
        return self.plan.save('owner', 'plan', baseline, changes, p['preview_fingerprint'], key)

    def node(self, oid, kind='event'):
        return {'id': oid, 'values': {'kind': kind, 'title': oid, 'summary': 'Synthetic candidate'}}

    def edge(self, oid, a, b, kind='depends_on'):
        return {'id': oid, 'relation_type': kind, 'from_id': a, 'to_id': b}

    def timed_node(self, oid, kind='event', **values):
        row = self.node(oid, kind)
        row['values'].update(values)
        return row

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
                    self.assertTrue({'story_plan_get', 'story_plan_preview', 'story_plan_save',
                                     'story_chapter_context', 'story_consistency_review'} <= set(tools))
                    self.assertTrue(tools['story_plan_get'].annotations.read_only_hint)
                    self.assertTrue(tools['story_chapter_context'].annotations.read_only_hint)
                    self.assertTrue(tools['story_consistency_review'].annotations.read_only_hint)
                    async def call(name, args):
                        r = await session.call_tool(name, args)
                        self.assertFalse(r.is_error)
                        data = json.loads(r.content[0].text)
                        self.assertTrue(data['ok'], data)
                        return data['result']
                    args = {'project': 'owner', 'dataset_id': 'plan', 'baseline': 2,
                            'change_set': {'nodes': [self.node('a', 'chapter')]}}
                    p = await call('story_plan_preview', args)
                    result = await call('story_plan_save', {**args, 'preview_fingerprint': p['preview_fingerprint'], 'operation_key': 'stdio'})
                    graph = await call('story_plan_get', {'project': 'owner', 'dataset_id': 'plan', 'dataset_revision': result['dataset_revision']})
                    self.assertEqual(graph['nodes'][0]['object_id'], 'a')
                    context = await call('story_chapter_context', {'project': 'owner', 'dataset_id': 'plan',
                                         'chapter_id': 'a', 'dataset_revision': result['dataset_revision']})
                    self.assertEqual(context['state'], 'READY')
                    review = await call('story_consistency_review', {'project': 'owner', 'dataset_id': 'plan',
                                        'dataset_revision': result['dataset_revision']})
                    self.assertFalse(review['findings'])
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

    def test_chapter_context_is_version_pinned_bounded_and_reader_safe(self):
        self.setup_plan()
        nodes = [self.node('c27', 'chapter'), self.node('current'), self.node('prior'),
                 self.node('person', 'character'), self.node('place', 'location'),
                 self.node('known', 'character_state'), self.node('setup', 'setup'),
                 self.node('thread', 'thread')]
        edges = [self.edge('c-event', 'c27', 'current', 'contains'),
                 self.edge('needs-prior', 'current', 'prior'),
                 self.edge('person-current', 'person', 'current', 'participates_in'),
                 self.edge('current-place', 'current', 'place', 'occurs_at'),
                 self.edge('current-known', 'current', 'known', 'requires_state'),
                 self.edge('prior-known', 'prior', 'known', 'establishes'),
                 self.edge('current-setup', 'current', 'setup', 'pays_off'),
                 self.edge('current-thread', 'current', 'thread', 'advances')]
        saved = self.commit({'nodes': nodes, 'edges': edges})
        context = self.plan.chapter_context('owner', 'plan', 'c27', saved['dataset_revision'])
        self.assertEqual(context['state'], 'READY')
        self.assertEqual({n['id'] for n in context['nodes']}, {n['id'] for n in nodes})
        self.assertFalse(context['coverage']['external_sources_loaded'])
        self.assertFalse(context['canon'])
        reader = self.plan.chapter_context('owner', 'plan', 'c27', saved['dataset_revision'], mode='reader')
        self.assertEqual(reader['state'], 'BLOCKED')
        self.assertFalse(reader['nodes'])
        limited = self.plan.chapter_context('owner', 'plan', 'c27', saved['dataset_revision'], max_nodes=2)
        self.assertEqual(limited['state'], 'PARTIAL')
        self.assertEqual(len(limited['nodes']), 2)
        self.assertTrue(any(x['code'] == 'context_budget' for x in limited['issues']))

    def test_consistency_review_proves_only_comparable_conflicts(self):
        self.setup_plan()
        nodes = [self.node('person', 'character'),
                 self.timed_node('e1', time_domain='main', time_start=10, time_end=20),
                 self.timed_node('e2', time_domain='main', time_start=15, time_end=25),
                 self.timed_node('later', time_domain='main', time_start=30, time_end=31),
                 self.timed_node('place-a', 'location', location_exclusive=True),
                 self.timed_node('place-b', 'location', location_exclusive=True),
                 self.timed_node('knowledge', 'character_state', state_key='knows-secret', state_value='yes'),
                 self.node('unknown-state', 'character_state')]
        edges = [self.edge('p-e1', 'person', 'e1', 'participates_in'),
                 self.edge('p-e2', 'person', 'e2', 'participates_in'),
                 self.edge('e1-a', 'e1', 'place-a', 'occurs_at'),
                 self.edge('e2-b', 'e2', 'place-b', 'occurs_at'),
                 self.edge('e1-needs', 'e1', 'knowledge', 'requires_state'),
                 self.edge('later-knows', 'later', 'knowledge', 'establishes'),
                 self.edge('e2-unknown', 'e2', 'unknown-state', 'requires_state')]
        saved = self.commit({'nodes': nodes, 'edges': edges})
        review = self.plan.consistency_review('owner', 'plan', saved['dataset_revision'])
        rules = {x['rule_id'] for x in review['findings']}
        self.assertIn('exclusive_location_overlap', rules)
        self.assertIn('state_established_too_late', rules)
        self.assertTrue(any(x['rule_id'] == 'state_origin_missing' for x in review['insufficient_evidence']))
        self.assertFalse(review['literary_quality_verified'])
        self.assertFalse(review['coverage']['full_project_verified'])

    def test_unknown_time_is_insufficient_not_a_conflict(self):
        self.setup_plan()
        nodes = [self.node('person', 'character'), self.node('e1'), self.node('e2'),
                 self.timed_node('place-a', 'location', location_exclusive=True),
                 self.timed_node('place-b', 'location', location_exclusive=True)]
        edges = [self.edge('p-e1', 'person', 'e1', 'participates_in'),
                 self.edge('p-e2', 'person', 'e2', 'participates_in'),
                 self.edge('e1-a', 'e1', 'place-a', 'occurs_at'),
                 self.edge('e2-b', 'e2', 'place-b', 'occurs_at')]
        saved = self.commit({'nodes': nodes, 'edges': edges})
        review = self.plan.consistency_review('owner', 'plan', saved['dataset_revision'],
                                              checks=['time_location'])
        self.assertFalse(review['findings'])
        self.assertTrue(any(x['rule_id'] == 'time_location_not_comparable'
                            for x in review['insufficient_evidence']))

    def test_invalid_time_range_is_rejected_on_planning_save(self):
        self.setup_plan()
        bad = self.timed_node('event', time_domain='main', time_start=20, time_end=10)
        with self.assertRaises(ValueError):
            self.commit({'nodes': [bad]})
