"""Rebuildable Markdown outline evidence, not semantic extraction or Canon."""
import re
from typing import Literal
from pydantic import Field
from knowledge_models import Model, ID, SHA
from manuscript_review import anchors


class FactProposal(Model):
    id: str = Field(pattern=ID)
    source_id: str = Field(pattern=ID)
    expected_fingerprint: str = Field(pattern=SHA)
    kind: Literal['story_contract', 'character', 'timeline']
    entity_id: str = Field(pattern=ID)
    field: str = Field(pattern=ID)
    value: str = Field(min_length=1, max_length=2000)
    quote: str = Field(min_length=1, max_length=3000)
    start_char: int | None = Field(default=None, ge=0)
    status_quote: str = Field(default='', max_length=3000)


def map_facts(documents, proposals):
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 20:
        raise ValueError('source_facts须为1至20项候选字段')
    parsed = [FactProposal.model_validate(x) for x in proposals]
    if len({x.id for x in parsed}) != len(parsed):
        raise ValueError('候选字段id不能重复')
    docs = {x['id']: x for x in documents if 'text' in x and not x.get('content_omitted')}
    result = []
    for proposal in parsed:
        if proposal.source_id not in docs:
            raise ValueError('候选字段须引用本次已交付文档，不自动扩展取材范围')
        doc = docs[proposal.source_id]
        base = doc.get('excerpt', {}).get('start_char', 0)
        row = {**proposal.model_dump(), 'path': doc['path'], 'authority': doc['authority'],
               'mapping_state': 'candidate', 'semantic_verified': False,
               'approval_state': 'not_inferred', 'canon': False}
        if proposal.expected_fingerprint != doc['fingerprint']:
            row['evidence_state'] = 'fingerprint_mismatch'
        else:
            request = {'id': proposal.id, 'quote': proposal.quote}
            if proposal.start_char is not None:
                if proposal.start_char < base:
                    row['evidence_state'] = 'outside_delivered_range'
                    result.append(row)
                    continue
                request['start_char'] = proposal.start_char - base
            evidence = anchors(doc['text'], [request])[0]
            if evidence['status'] == 'anchored':
                for key in ('start_char', 'end_char'):
                    evidence[key] += base
                for key in ('start_line', 'end_line'):
                    evidence[key] += doc.get('excerpt', {}).get('start_line', 1) - 1
            row['evidence'] = evidence
            row['evidence_state'] = evidence['status']
            if proposal.status_quote:
                row['status_evidence'] = anchors(doc['text'], [dict(id='status', quote=proposal.status_quote)])[0]
                if row['status_evidence']['status'] == 'anchored':
                    for key in ('start_char', 'end_char'):
                        row['status_evidence'][key] += base
                    for key in ('start_line', 'end_line'):
                        row['status_evidence'][key] += doc.get('excerpt', {}).get('start_line', 1) - 1
                row['status_evidence']['scope'] = '仅证明状态文字存在；不认证其适用于该字段。'
        result.append(row)
    return result

HEADING = re.compile(r'^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*(?:\r?\n)?$')
CHAPTER = re.compile(r'^第[一二三四五六七八九十百千万零〇两0-9]+[章回]')


def build(documents, limit=100, fact_proposals=None):
    rows = []
    observed_chapters = 0
    total_headings = 0
    scanned = []
    for doc in documents:
        if 'text' not in doc or doc.get('content_omitted'):
            continue
        text = doc['text']
        excerpt = doc.get('excerpt', {})
        base = excerpt.get('start_char', 0)
        line_base = excerpt.get('start_line', 1)
        scanned.append({'source_id': doc['id'], 'path': doc['path'],
                        'fingerprint': doc['fingerprint'], 'char_start': base,
                        'char_end': base + len(text),
                        'whole_document_delivered': not bool(excerpt)})
        headings = []
        offset = 0
        fence = None
        for index, line in enumerate(text.splitlines(keepends=True)):
            stripped = line.lstrip(' ')
            marker = re.match(r'(`{3,}|~{3,})', stripped) if len(line)-len(stripped) <= 3 else None
            if marker:
                token = marker.group(1)
                if fence is None:
                    fence = token
                elif token[0] == fence[0] and len(token) >= len(fence) and not stripped[len(token):].strip():
                    fence = None
                offset += len(line)
                continue
            match = HEADING.match(line) if fence is None else None
            if index == 0 and base and not excerpt.get('starts_at_line_boundary', False):
                match = None
            if match:
                headings.append((len(match[1]), match[2].strip(), offset, line_base + index))
            offset += len(line)
        for index, (level, title, offset, line_number) in enumerate(headings):
            total_headings += 1
            kind = 'chapter_heading' if doc['authority'] == 'working_manuscript' and CHAPTER.match(title) else 'document_heading'
            observed_chapters += kind == 'chapter_heading'
            if len(rows) < limit:
                end = next((headings[j][2] for j in range(index+1, len(headings))
                            if headings[j][0] <= level), len(text))
                rows.append({'source_id': doc['id'], 'path': doc['path'], 'fingerprint': doc['fingerprint'],
                             'kind': kind, 'title': title, 'heading_level': level,
                             'start_char': base + offset, 'end_char': base + end,
                             'start_line': line_number, 'authority': doc['authority'],
                             'end_boundary': 'next_heading' if end < len(text) else ('excerpt_end' if excerpt else 'file_end'),
                             'approval_state': 'not_inferred', 'canon': False})
    result = {'kind': 'markdown_outline_projection', 'sources': scanned, 'items': rows,
            'observed_chapter_headings': observed_chapters, 'items_truncated': total_headings > len(rows),
            'characters': {'state': 'not_mapped', 'count': None},
            'timeline': {'state': 'not_mapped', 'count': None},
            'story_contract': {'state': 'not_mapped', 'reason': '须逐字段核对原段落及批准范围，标题索引不推断内容。'},
            'semantic_verified': False, 'saved': False,
            'scope': '仅索引本次已核验读取的Markdown标题，不覆盖未选/未读内容；标题索引不表示正文已阅读，不替代_storylab，不批准Canon。'}
    if fact_proposals is not None:
        result['fact_candidates'] = map_facts(documents, fact_proposals)
        result['fact_scope'] = 'Chat提出字段含义，程序仅核对原文引用；引文匹配不证明value或批准状态正确。'
        groups = {}
        for row in result['fact_candidates']:
            if row['evidence_state'] == 'anchored':
                groups.setdefault((row['kind'], row['entity_id'], row['field']), []).append(row)
        result['field_conflicts'] = [
            {'kind': key[0], 'entity_id': key[1], 'field': key[2],
             'candidate_ids': [x['id'] for x in group], 'state': 'review_required'}
            for key, group in groups.items() if len({x['value'] for x in group}) > 1]
        for kind, section in [('character', 'characters'), ('timeline', 'timeline'), ('story_contract', 'story_contract')]:
            matching = [x for x in result['fact_candidates'] if x['kind'] == kind and x['evidence_state'] == 'anchored']
            if matching:
                result[section] = {'state': 'evidence_anchored_candidates',
                                   'candidate_entity_count': len({x['entity_id'] for x in matching}),
                                   'candidate_field_count': len(matching), 'approved_count': None}
    return result
