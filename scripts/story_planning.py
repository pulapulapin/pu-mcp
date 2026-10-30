"""Bounded candidate graphs backed by existing Knowledge versions and journal."""
from collections import deque
from typing import Literal
from pydantic import Field
from knowledge_data import Knowledge
from knowledge_models import Model, Binding, ID, Structure
from novel_evidence import encode
from novel_store import digest, identifier

RELATIONS = ['contains', 'depends_on', 'precedes', 'participates_in', 'occurs_at',
             'establishes', 'requires_state', 'pays_off', 'advances', 'supersedes']
KINDS = ['volume', 'unit', 'chapter', 'scene', 'event', 'character',
         'relationship_state', 'character_state', 'thread', 'setup', 'location', 'decision']
SCHEMA = {'fields': {
    'kind': {'type': 'string', 'required': True, 'enum': KINDS},
    'title': {'type': 'string', 'required': True},
    'summary': {'type': 'string', 'required': True},
    'story_state': {'type': 'string', 'required': True, 'enum': ['candidate']},
    **{key: {'type': 'string'} for key in ('goal', 'obstacle', 'action', 'turn', 'outcome')},
}, 'allowed_relations': RELATIONS}


class NodeValues(Model):
    kind: Literal['volume', 'unit', 'chapter', 'scene', 'event', 'character',
                  'relationship_state', 'character_state', 'thread', 'setup', 'location', 'decision']
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=10000)
    story_state: Literal['candidate'] = 'candidate'
    goal: str = Field(default='', max_length=10000)
    obstacle: str = Field(default='', max_length=10000)
    action: str = Field(default='', max_length=10000)
    turn: str = Field(default='', max_length=10000)
    outcome: str = Field(default='', max_length=10000)


class NodeChange(Model):
    id: str = Field(pattern=ID)
    values: NodeValues
    status: Literal['candidate', 'withdrawn'] = 'candidate'
    evidence: list[Binding] = Field(default_factory=list, max_length=30)


class EdgeChange(Model):
    id: str = Field(pattern=ID)
    relation_type: Literal['contains', 'depends_on', 'precedes', 'participates_in', 'occurs_at',
                           'establishes', 'requires_state', 'pays_off', 'advances', 'supersedes']
    from_id: str = Field(pattern=ID)
    to_id: str = Field(pattern=ID)
    status: Literal['candidate', 'withdrawn'] = 'candidate'


class ChangeSet(Model):
    nodes: list[NodeChange] = Field(default_factory=list, max_length=100)
    edges: list[EdgeChange] = Field(default_factory=list, max_length=200)


def normalize(changes):
    value = ChangeSet.model_validate(changes).model_dump(mode='json')
    if not value['nodes'] and not value['edges']:
        raise ValueError('change_set is empty')
    if len(encode(value).encode()) > 262144:
        raise ValueError('change_set exceeds 256KiB')
    for key in ('nodes', 'edges'):
        ids = [row['id'] for row in value[key]]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate ' + key + ' id')
    return value


class StoryPlanning:
    def __init__(self, workspace):
        self.w = workspace
        self.k = Knowledge(workspace)

    def _access(self, db, project, dataset, write=False):
        meta = self.k._access(db, project, dataset, write)['body']
        if meta['scope'] != 'project' or meta['purpose'] != 'model':
            raise ValueError('story planning requires a project-private model dataset')

    def _graph(self, db, project, dataset, revision):
        self._access(db, project, dataset)
        self.k._snapshot(db, dataset, revision)
        nodes = self.k._latest(db, 'record', dataset, revision)
        edges = self.k._latest(db, 'relation', dataset, revision)
        if len(nodes) > 2000 or len(edges) > 6000:
            raise ValueError('graph exceeds 2000 nodes / 6000 edges; scope into separate datasets')
        if any(row['body']['record_type'] != 'story_node' for row in nodes):
            raise ValueError('dataset contains non-story records')
        nodes = {r['object_id']: r for r in nodes if r['body']['status'] != 'withdrawn'}
        edges = {r['object_id']: r for r in edges if r['body']['status'] != 'withdrawn'}
        stale = []
        for eid, row in edges.items():
            for side in ('from', 'to'):
                endpoint = row['body'][side]
                target = nodes.get(endpoint['record_id'])
                if endpoint['dataset_id'] != dataset:
                    raise ValueError('story edges must stay within their dataset')
                if not target or target['revision'] != endpoint['revision'] or target['fingerprint'] != endpoint['fingerprint']:
                    stale.append({'relation_id': eid, 'side': side, 'code': 'endpoint_superseded_or_withdrawn',
                                  'endpoint': endpoint})
        return nodes, edges, stale

    def get(self, project, dataset_id, dataset_revision=0, offset=0, limit=50):
        if any(type(x) is not int or x < 0 for x in (dataset_revision, offset)) or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('invalid snapshot or page')
        with self.k.store.connection() as db:
            self._access(db, project, dataset_id)
            version = dataset_revision or self.k.revision(dataset_id, db)
            nodes, edges, stale = self._graph(db, project, dataset_id, version)
            items = [('nodes', r) for r in nodes.values()] + [('edges', r) for r in edges.values()]
            page = items[offset:offset+limit]
            # Raw fixed references only; do not fetch other project/source content.
            result = {'nodes': [], 'edges': [], 'dataset_revision': version,
                      'total': len(items), 'next_offset': offset+limit if offset+limit < len(items) else None,
                      'stale_endpoints': stale[:50], 'stale_endpoint_count': len(stale),
                      'stale_endpoints_truncated': len(stale) > 50, 'canon': False,
                      'coverage': 'registered_candidate_graph_only', 'full_project_verified': False}
            for key, row in page:
                result[key].append({k: row[k] for k in ('object_id', 'revision', 'fingerprint', 'body')} |
                                   {'dataset_revision': row['commit_revision'], 'canon': False})
            return result

    def _validate_graph(self, nodes, edges):
        parents = {}
        for kind in ('contains', 'depends_on'):
            adjacency = {key: [] for key in nodes}
            for row in edges.values():
                body = row['body']
                if body['relation_type'] != kind:
                    continue
                a, b = body['from']['record_id'], body['to']['record_id']
                if a not in nodes or b not in nodes:
                    continue  # reported stale, not silently repaired
                adjacency[a].append(b)
                if kind == 'contains':
                    ka, kb = nodes[a]['body']['values']['kind'], nodes[b]['body']['values']['kind']
                    allowed = {'volume': {'unit', 'chapter'}, 'unit': {'unit', 'chapter'},
                               'chapter': {'scene', 'event'}, 'scene': {'event'}}
                    if kb not in allowed.get(ka, set()):
                        raise ValueError('invalid contains kinds')
                    if b in parents and parents[b] != a:
                        raise ValueError('multiple contains parents')
                    parents[b] = a
            # Iterative topological check avoids recursion failures on long novels.
            degree = {key: 0 for key in nodes}
            for targets in adjacency.values():
                for key in targets: degree[key] += 1
            queue = deque(k for k, value in degree.items() if not value)
            count = 0
            while queue:
                count += 1
                for key in adjacency[queue.popleft()]:
                    degree[key] -= 1
                    if not degree[key]: queue.append(key)
            if count != len(nodes):
                raise ValueError(kind + ' cycle')

    def _impact(self, seeds, graphs):
        paths, chapters = [], set()
        truncated = False
        for label, (nodes, edges, _) in zip(('before', 'after'), graphs):
            reverse = {}
            for eid, row in edges.items():
                b = row['body']
                if b['relation_type'] in ('depends_on', 'contains'):
                    reverse.setdefault(b['to']['record_id'], []).append((b['from']['record_id'], eid))
            for seed in sorted(seeds):
                queue, seen = deque([(seed, [])]), {seed}
                while queue:
                    current, path = queue.popleft()
                    if current in nodes and nodes[current]['body']['values']['kind'] == 'chapter':
                        chapters.add(current)
                    for target, eid in reverse.get(current, []):
                        if target in seen: continue
                        seen.add(target)
                        if len(paths) >= 200 or len(path) >= 32:
                            truncated = True
                            queue.clear()
                            break
                        route = path + [eid]
                        paths.append({'graph': label, 'seed': seed, 'target_id': target,
                                      'relation_ids': route,
                                      'relation_refs': [{'id': r, 'revision': edges[r]['revision'],
                                                         'fingerprint': edges[r]['fingerprint']} for r in route]})
                        queue.append((target, route))
                if truncated: break
            if truncated: break
        return {'chapter_ids': sorted(chapters), 'paths': paths, 'truncated': truncated,
                'coverage': 'explicit_reverse_dependencies_and_containment_only',
                'semantic_impacts_verified': False}

    def _apply(self, db, project, dataset, baseline, changes):
        self._access(db, project, dataset, True)
        if type(baseline) is not int or baseline != self.k.revision(dataset, db):
            raise ValueError('dataset baseline conflict')
        schema = self.k._row(db, 'schema', dataset, 'story_node')
        expected = Structure.model_validate(SCHEMA).model_dump(mode='json')
        if schema['body'] != expected:
            raise ValueError('story_node schema differs from the supported schema pack')
        before = self._graph(db, project, dataset, baseline)
        diffs, refs = [], []
        withdrawals = {}
        # Validate removal against the old graph before withdrawing its nodes.
        for row in changes['edges']:
            if row['status'] != 'withdrawn':
                continue
            old = self.k._row(db, 'relation', dataset, row['id'])['body']
            if (old['relation_type'], old['from']['record_id'], old['to']['record_id']) != (row['relation_type'], row['from_id'], row['to_id']):
                raise ValueError('withdrawal must reference the existing edge')
            withdrawals[row['id']] = {**old, 'status': 'withdrawn'}
        for row in changes['nodes']:
            body = {'record_type': 'story_node', 'schema_revision': schema['revision'],
                    'values': row['values'], 'status': row['status'], 'evidence': row['evidence']}
            normalized = self.k._prepare(db, project, 'record', dataset, row['id'], body)
            try: old = self.k._row(db, 'record', dataset, row['id'])['body']
            except ValueError: old = None
            diffs.append({'kind': 'record', 'id': row['id'], 'before': old, 'after': normalized})
            refs.append(self.k._insert(db, 'record', dataset, row['id'], normalized, baseline+1))
        for row in changes['edges']:
            body = {'relation_type': row['relation_type'], 'status': row['status']}
            for side, key in (('from', 'from_id'), ('to', 'to_id')):
                target = self.k._row(db, 'record', dataset, row[key])
                body[side] = {'dataset_id': dataset, 'record_id': row[key],
                              'revision': target['revision'], 'fingerprint': target['fingerprint']}
            normalized = withdrawals.get(row['id'])
            if normalized is None:
                normalized = self.k._prepare(db, project, 'relation', dataset, row['id'], body)
            try: old = self.k._row(db, 'relation', dataset, row['id'])['body']
            except ValueError: old = None
            diffs.append({'kind': 'relation', 'id': row['id'], 'before': old, 'after': normalized})
            refs.append(self.k._insert(db, 'relation', dataset, row['id'], normalized, baseline+1))
        after = self._graph(db, project, dataset, baseline+1)
        self._validate_graph(*after[:2])
        seeds = {r['id'] for r in changes['nodes']}
        # Removed/changed dependencies must still expose their old effects.
        for row in changes['edges']:
            seeds.update((row['from_id'], row['to_id']))
            old = before[1].get(row['id'])
            if old: seeds.update(old['body'][s]['record_id'] for s in ('from', 'to'))
        return {'baseline': baseline, 'changes': diffs, 'references': refs,
                'impact': self._impact(seeds, (before, after)), 'stale_endpoints': after[2][:50],
                'stale_endpoint_count': len(after[2]), 'stale_endpoints_truncated': len(after[2]) > 50,
                'canon': False, 'fact_verification': 'not_verified'}

    def preview(self, project, dataset_id, baseline, change_set):
        changes = normalize(change_set)
        with self.k.store.connection(write=True) as db:
            db.execute('SAVEPOINT story_preview')
            try:
                result = self._apply(db, project, dataset_id, baseline, changes)
            finally:
                db.execute('ROLLBACK TO story_preview')
                db.execute('RELEASE story_preview')
            result['preview_fingerprint'] = digest(encode({'project': project, 'dataset_id': dataset_id,
                                                         'baseline': baseline, 'change_set': changes}))
            return result

    def save(self, project, dataset_id, baseline, change_set, preview_fingerprint, operation_key):
        changes = normalize(change_set)
        request = {'project': project, 'dataset_id': dataset_id, 'baseline': baseline,
                   'change_set': changes, 'preview_fingerprint': preview_fingerprint}
        expected = digest(encode({key: value for key, value in request.items() if key != 'preview_fingerprint'}))
        if preview_fingerprint != expected:
            raise ValueError('preview fingerprint mismatch')
        namespace = 'story-planning:' + project
        with self.k.store.connection(write=True) as db:
            self._access(db, project, dataset_id, True)
            previous = self.w.evidence.retry(db, namespace, operation_key, request)
            if previous: return previous
            result = self._apply(db, project, dataset_id, baseline, changes)
            reply = {'dataset_revision': baseline+1, 'references': result['references'], 'canon': False}
            self.w.evidence.operation(db, namespace, operation_key, request, reply)
            return reply
