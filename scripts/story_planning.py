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
    'story_order': {'type': 'integer', 'minimum': 0},
    'time_domain': {'type': 'string'},
    'time_start': {'type': 'integer'},
    'time_end': {'type': 'integer'},
    'time_precision': {'type': 'string'},
    'location_exclusive': {'type': 'boolean'},
    'state_key': {'type': 'string'},
    'state_value': {'type': 'string'},
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
    story_order: int | None = Field(default=None, ge=0)
    time_domain: str = Field(default='', max_length=200)
    time_start: int | None = None
    time_end: int | None = None
    time_precision: str = Field(default='', max_length=80)
    location_exclusive: bool | None = None
    state_key: str = Field(default='', max_length=200)
    state_value: str = Field(default='', max_length=10000)


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
    value = ChangeSet.model_validate(changes).model_dump(mode='json', exclude_none=True)
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

    @staticmethod
    def _node_ref(row):
        return {'id': row['object_id'], 'revision': row['revision'],
                'fingerprint': row['fingerprint'], 'dataset_revision': row['commit_revision'],
                'values': row['body']['values'], 'evidence': row['body']['evidence'],
                'record_status': row['body']['status'], 'canon': False}

    @staticmethod
    def _edge_ref(row):
        body = row['body']
        return {'id': row['object_id'], 'revision': row['revision'],
                'fingerprint': row['fingerprint'], 'dataset_revision': row['commit_revision'],
                'relation_type': body['relation_type'], 'from': body['from'], 'to': body['to'],
                'canon': False}

    def chapter_context(self, project, dataset_id, chapter_id, dataset_revision=0,
                        mode='author', max_nodes=200):
        identifier(chapter_id)
        if mode not in ('author', 'reader'):
            raise ValueError('mode must be author or reader')
        if type(max_nodes) is not int or not 1 <= max_nodes <= 500:
            raise ValueError('max_nodes must be 1..500')
        with self.k.store.connection() as db:
            version = dataset_revision or self.k.revision(dataset_id, db)
            nodes, edges, stale = self._graph(db, project, dataset_id, version)
            chapter = nodes.get(chapter_id)
            if not chapter or chapter['body']['values']['kind'] != 'chapter':
                raise ValueError('chapter does not exist at the selected snapshot')
            if mode == 'reader':
                return {'state': 'BLOCKED', 'dataset_revision': version, 'chapter_id': chapter_id,
                        'mode': mode, 'nodes': [], 'edges': [], 'canon': False,
                        'issues': [{'code': 'candidate_graph_not_reader_material',
                                    'reason': 'Candidate planning data is not manuscript evidence and is withheld from reader mode.'}],
                        'coverage': {'selected_graph': False, 'external_sources_loaded': False,
                                     'full_project_verified': False}}

            stale_ids = {item['relation_id'] for item in stale}
            active_edges = {eid: row for eid, row in edges.items() if eid not in stale_ids}
            outgoing, incoming = {}, {}
            for eid, row in active_edges.items():
                body = row['body']; a = body['from']['record_id']; b = body['to']['record_id']
                outgoing.setdefault(a, []).append((eid, body['relation_type'], b))
                incoming.setdefault(b, []).append((eid, body['relation_type'], a))

            selected, reasons = {chapter_id}, {chapter_id: {'chapter'}}
            queue = deque([chapter_id])
            while queue:
                current = queue.popleft()
                for eid, kind, target in outgoing.get(current, []):
                    if kind == 'contains' and target not in selected:
                        selected.add(target); reasons[target] = {'chapter_descendant'}; queue.append(target)

            prerequisite_queue = deque(sorted(selected))
            visited = set(selected)
            while prerequisite_queue:
                current = prerequisite_queue.popleft()
                for eid, kind, target in outgoing.get(current, []):
                    if kind == 'depends_on' and target not in visited:
                        visited.add(target); selected.add(target)
                        reasons.setdefault(target, set()).add('explicit_prerequisite')
                        prerequisite_queue.append(target)

            changed = True
            while changed:
                changed = False
                for eid, row in active_edges.items():
                    body = row['body']; kind = body['relation_type']
                    a, b = body['from']['record_id'], body['to']['record_id']
                    include = (kind == 'participates_in' and b in selected or
                               kind in ('occurs_at', 'requires_state', 'pays_off', 'advances') and a in selected or
                               kind == 'establishes' and (a in selected or b in selected))
                    if include:
                        for node_id, reason in ((a, kind + '_source'), (b, kind + '_target')):
                            if node_id in nodes and node_id not in selected:
                                selected.add(node_id); reasons.setdefault(node_id, set()).add(reason); changed = True

            ordered = sorted(selected, key=lambda key: (
                nodes[key]['body']['values'].get('story_order', 10**9), key))
            truncated = len(ordered) > max_nodes
            delivered = set(ordered[:max_nodes])
            selected_edges = [row for row in active_edges.values()
                              if row['body']['from']['record_id'] in delivered and
                              row['body']['to']['record_id'] in delivered]
            issues = []
            if stale:
                issues.append({'code': 'stale_relations', 'count': len(stale),
                               'relation_ids': sorted(stale_ids)[:50]})
            if truncated:
                issues.append({'code': 'context_budget', 'selected': len(ordered),
                               'delivered': len(delivered), 'deferred_ids': ordered[max_nodes:max_nodes+50]})
            return {'state': 'PARTIAL' if issues else 'READY',
                    'readiness_scope': 'registered_story_graph_only',
                    'dataset_revision': version,
                    'chapter_id': chapter_id, 'mode': mode,
                    'nodes': [self._node_ref(nodes[key]) | {'selection_reasons': sorted(reasons.get(key, set()))}
                              for key in ordered if key in delivered],
                    'edges': [self._edge_ref(row) for row in selected_edges],
                    'issues': issues, 'canon': False,
                    'coverage': {'selected_graph': not truncated, 'registered_relations_only': True,
                                 'external_sources_loaded': False, 'full_project_verified': False,
                                 'reader_future_plan_excluded': True}}

    def consistency_review(self, project, dataset_id, dataset_revision=0,
                           scope_ids=None, checks=None, max_findings=100):
        scope_ids = scope_ids or []
        checks = checks or ['structural', 'time_location', 'knowledge']
        if len(scope_ids) > 200 or any(not isinstance(x, str) for x in scope_ids):
            raise ValueError('scope_ids must contain at most 200 ids')
        if not checks or len(checks) > 3 or any(x not in ('structural', 'time_location', 'knowledge') for x in checks):
            raise ValueError('unknown consistency check')
        if type(max_findings) is not int or not 1 <= max_findings <= 200:
            raise ValueError('max_findings must be 1..200')
        with self.k.store.connection() as db:
            version = dataset_revision or self.k.revision(dataset_id, db)
            nodes, edges, stale = self._graph(db, project, dataset_id, version)
            missing = sorted(set(scope_ids) - set(nodes))
            selected = set(scope_ids) if scope_ids else set(nodes)
            stale_ids = {x['relation_id'] for x in stale}
            usable = {eid: row for eid, row in edges.items() if eid not in stale_ids}
            if scope_ids:
                changed = True
                while changed:
                    changed = False
                    for row in usable.values():
                        body = row['body']; kind = body['relation_type']
                        a, b = body['from']['record_id'], body['to']['record_id']
                        include = (kind == 'contains' and a in selected or
                                   kind == 'participates_in' and b in selected or
                                   kind == 'participates_in' and a in selected or
                                   kind in ('occurs_at', 'requires_state', 'pays_off', 'advances') and a in selected or
                                   kind == 'establishes' and (a in selected or b in selected))
                        if include:
                            for key in (a, b):
                                if key in nodes and key not in selected:
                                    selected.add(key); changed = True
            findings, insufficient = [], []

            def add(target, item):
                if len(target) < max_findings: target.append(item)

            if 'structural' in checks:
                try:
                    self._validate_graph(nodes, usable)
                except ValueError as exc:
                    add(findings, {'rule_id': 'graph_constraint', 'severity': 'error',
                                   'object_ids': [], 'evidence': {'message': str(exc)},
                                   'fact_scope': 'registered_graph'})
                for item in stale:
                    add(findings, {'rule_id': 'stale_endpoint', 'severity': 'error',
                                   'object_ids': [item['relation_id']], 'evidence': item,
                                   'fact_scope': 'registered_graph'})
                if missing:
                    add(insufficient, {'rule_id': 'missing_scope', 'object_ids': missing[:50],
                                       'reason': 'Requested ids do not exist in this snapshot.'})
                for key in sorted(selected & set(nodes)):
                    values = nodes[key]['body']['values']
                    if (type(values.get('time_start')) is int and type(values.get('time_end')) is int and
                            values['time_start'] > values['time_end']):
                        add(findings, {'rule_id': 'invalid_time_range', 'severity': 'error',
                                       'object_ids': [key], 'evidence': {
                                           'time_start': values['time_start'], 'time_end': values['time_end']},
                                       'fact_scope': 'registered_graph'})

            character_events, event_locations = {}, {}
            for eid, row in usable.items():
                body = row['body']; kind = body['relation_type']
                a, b = body['from']['record_id'], body['to']['record_id']
                if kind == 'participates_in' and (a in selected or b in selected):
                    character_events.setdefault(a, []).append((b, eid))
                elif kind == 'occurs_at':
                    event_locations.setdefault(a, []).append((b, eid))

            if 'time_location' in checks:
                for character, event_refs in character_events.items():
                    if len(event_refs) > 200:
                        add(insufficient, {'rule_id': 'character_event_scope_truncated',
                                           'object_ids': [character],
                                           'reason': 'More than 200 registered events; review a narrower scope.'})
                        event_refs = event_refs[:200]
                    for index, (left, left_edge) in enumerate(event_refs):
                        for right, right_edge in event_refs[index+1:]:
                            lv = nodes[left]['body']['values']; rv = nodes[right]['body']['values']
                            comparable = (
                                lv.get('time_domain') and
                                lv.get('time_domain') == rv.get('time_domain') and
                                all(type(v) is int for v in (
                                    lv.get('time_start'), lv.get('time_end'),
                                    rv.get('time_start'), rv.get('time_end')))
                            )
                            if not comparable:
                                add(insufficient, {'rule_id': 'time_location_not_comparable',
                                                   'object_ids': [character, left, right],
                                                   'reason': 'Events lack comparable domain and closed integer ranges.'})
                                continue
                            if max(lv['time_start'], rv['time_start']) > min(lv['time_end'], rv['time_end']):
                                continue
                            left_places = [(place, edge) for place, edge in event_locations.get(left, [])
                                           if nodes.get(place, {}).get('body', {}).get('values', {}).get('location_exclusive') is True]
                            right_places = [(place, edge) for place, edge in event_locations.get(right, [])
                                            if nodes.get(place, {}).get('body', {}).get('values', {}).get('location_exclusive') is True]
                            pairs = [(a, ea, b, eb) for a, ea in left_places for b, eb in right_places if a != b]
                            if pairs:
                                a, ea, b, eb = pairs[0]
                                add(findings, {'rule_id': 'exclusive_location_overlap', 'severity': 'error',
                                               'object_ids': [character, left, right, a, b],
                                               'relation_ids': [left_edge, right_edge, ea, eb],
                                               'time_domain': lv['time_domain'],
                                               'overlap': [max(lv['time_start'], rv['time_start']),
                                                           min(lv['time_end'], rv['time_end'])],
                                               'fact_scope': 'registered_candidate_graph'})

            if 'knowledge' in checks:
                establishes = {}
                requirements = []
                for eid, row in usable.items():
                    body = row['body']; kind = body['relation_type']
                    a, b = body['from']['record_id'], body['to']['record_id']
                    if kind == 'establishes': establishes.setdefault(b, []).append((a, eid))
                    elif kind == 'requires_state' and (a in selected or b in selected): requirements.append((a, b, eid))
                for event, state, requirement_edge in requirements:
                    ev = nodes[event]['body']['values']; candidates = establishes.get(state, [])
                    if not candidates:
                        add(insufficient, {'rule_id': 'state_origin_missing', 'object_ids': [event, state],
                                           'relation_ids': [requirement_edge],
                                           'reason': 'No explicit establishes relation was registered.'})
                        continue
                    comparable = []
                    for source, establish_edge in candidates:
                        sv = nodes[source]['body']['values']
                        if (ev.get('time_domain') and
                                ev.get('time_domain') == sv.get('time_domain') and
                                type(ev.get('time_start')) is int and
                                type(sv.get('time_start')) is int):
                            comparable.append((source, establish_edge, sv['time_start']))
                    if not comparable:
                        add(insufficient, {'rule_id': 'state_time_not_comparable', 'object_ids': [event, state],
                                           'reason': 'Requirement and establishment lack comparable time points.'})
                    elif min(x[2] for x in comparable) > ev['time_start']:
                        source, establish_edge, when = min(comparable, key=lambda x: x[2])
                        add(findings, {'rule_id': 'state_established_too_late', 'severity': 'error',
                                       'object_ids': [event, state, source],
                                       'relation_ids': [requirement_edge, establish_edge],
                                       'required_at': ev['time_start'], 'established_at': when,
                                       'fact_scope': 'registered_candidate_graph'})

            return {'dataset_revision': version, 'findings': findings,
                    'insufficient_evidence': insufficient,
                    'finding_count': len(findings), 'insufficient_count': len(insufficient),
                    'truncated': len(findings) >= max_findings or len(insufficient) >= max_findings,
                    'canon': False, 'literary_quality_verified': False,
                    'review_scope': 'registered_candidate_graph_only',
                    'coverage': {'scope_ids': sorted(selected)[:200], 'checks': checks,
                                 'registered_relations_only': True, 'external_sources_loaded': False,
                                 'full_project_verified': False}}

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
            values = row['values']
            if (type(values.get('time_start')) is int and type(values.get('time_end')) is int and
                    values['time_start'] > values['time_end']):
                raise ValueError('time_start must be <= time_end')
            if values.get('location_exclusive') is not None and values['kind'] != 'location':
                raise ValueError('location_exclusive is only valid for location nodes')
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
