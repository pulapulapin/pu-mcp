"""Work ownership is structural, not keyword co-occurrence or rule verification."""
import re
from novel_books import CATALOG
from novel_research import edition_references, matches_edition, validate_filters

TITLES = {key: value[0] for key,value in CATALOG.items()}

def owners(text,titles=None):
    return {key for key,title in (titles or TITLES).items() if title in text}

def cells(line):
    # Escaped pipes are not column separators.
    return [c.strip().replace('\\|', '|') for c in re.split(r'(?<!\\)\|', line.strip().strip('|'))]

def units(body, work_id,titles=None):
    stack, table_headers, table_owners = [], None, None
    lines = body.splitlines()
    for number, line in enumerate(lines, 1):
        heading = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading:
            level = len(heading[1])
            stack = [s for s in stack if s[0]<level]
            stack.append((level, owners(heading[2],titles)))
            table_headers = table_owners = None
            continue
        section = next((s[1] for s in reversed(stack) if s[1]), set())
        if line.strip().startswith('|'):
            columns = cells(line)
            if all(re.fullmatch(r':?-{2,}:?', c.replace(' ','')) for c in columns):
                continue
            if table_headers is None:
                table_headers, table_owners = columns, [owners(c,titles) for c in columns]
                continue
            row_owners = owners(line,titles)
            # Works as columns: return that cell plus unlabeled descriptor columns only.
            selected = [i for i,o in enumerate(table_owners) if o == {work_id}]
            if selected:
                labels = [i for i,o in enumerate(table_owners) if not o and i < min(selected)]
                indexes = labels+selected
                text = ' | '.join(f'{table_headers[i]}: {columns[i]}' for i in indexes if i<len(columns))
                if owners(text,titles)-{work_id}:
                    continue
                yield number, number, text, 'table_column', indexes
            elif any(table_owners):
                # A mention inside another work's column cannot reassign that row.
                continue
            elif row_owners == {work_id} and columns and columns[0].strip(' *`《》') == titles[work_id]:
                yield number, number, line, 'table_row', []
            elif not row_owners and section == {work_id}:
                yield number, number, line, 'work_section_table', []
            continue
        table_headers = table_owners = None
        if section != {work_id} or owners(line,titles)-{work_id} or not line.strip():
            continue
        # Keep a paragraph as the unit, rather than merging adjacent unrelated summaries.
        if number>1 and lines[number-2].strip() and not lines[number-2].startswith('#') and not lines[number-2].strip().startswith('|'):
            continue
        paragraph = [line]
        end = number
        for following in lines[number:]:
            if not following.strip() or following.startswith('#') or following.strip().startswith('|'):
                break
            paragraph.append(following)
            end += 1
        text = '\n'.join(paragraph)
        if len(text)>6000 or owners(text,titles)-{work_id}:
            continue
        yield number, end, text, 'work_section', []

def search(store, query, limit, collection, edition_filter, path_prefix, match_mode, work_id):
    validate_filters(edition_filter,path_prefix,match_mode)
    from novel_books import Books
    books=Books(store)
    titles={key:value[0] for key,value in books.catalog.items()}
    if work_id not in titles or not books.registry(work_id)['active']:
        raise ValueError('work_id未配置；请使用参考小说列表中的work_id')
    if not isinstance(query,str) or not query.strip() or len(query)>500 or not 1 <= limit <=20:
        raise ValueError('查询1–500字，limit1–20')
    terms = list(dict.fromkeys(re.findall(r'[^\s,，。；;？?、]+', query.lower())))[:12]
    # Explicit work filter supplies the work identity; it need not repeat in every cell.
    terms = [t for t in terms if t != titles[work_id].lower()]
    if not terms:
        raise ValueError('选择作品后还需要研究关键词')
    with store.connection() as db:
        sources = db.execute('''SELECT s.*,v.body FROM sources s JOIN source_versions v
            ON v.source_id=s.id AND v.fingerprint=s.fingerprint WHERE s.active=1
            AND (?='' OR s.collection=?) AND (?='' OR instr(s.path,?)=1)''',
            (collection,collection,path_prefix,path_prefix)).fetchall()
    hits, before, related = [], 0, []
    for source in sources:
        if titles[work_id] not in source['body']:
            continue
        direct = False
        for first,last,text,unit_kind,columns in units(source['body'],work_id,titles):
            found = [term in text.lower() for term in terms]
            if not (all(found) if match_mode=='all' else any(found)):
                continue
            before += 1
            refs = edition_references(source['path'],text)
            from novel_library import annotated_reference
            refs=annotated_reference(store,source['id'],source['fingerprint'],refs)
            if not matches_edition(refs,edition_filter):
                continue
            direct = True
            hits.append({'source_id':source['id'],'collection':source['collection'],'path':source['path'],
                'fingerprint':source['fingerprint'],'source_fingerprint':source['fingerprint'],
                'line_start':first,'line_end':last,'body':text,'work_id':work_id,'work_title':titles[work_id],
                'section_id':f'L{first}-L{last}', 'column_indexes':columns,'unit_kind':unit_kind,
                'evidence_relation':'direct_work_record', 'evidence_type':'research_summary',
                'evidence_status':'作品归属已按结构定位；二次研究资料，原文事实仍需核对，非Canon', **refs})
        if not direct and any(t in source['body'].lower() for t in terms):
            related.append({'source_id':source['id'],'path':source['path'],'fingerprint':source['fingerprint'],
                'evidence_relation':'related_document','notice':'仅为相关文档；未找到可归属于指定作品的匹配单元，不作为直接证据'})
    hits.sort(key=lambda r:(r['collection'],r['path'],r['line_start']))
    return {'query':query,'hits':hits[:limit], 'total_matching_chunks':len(hits),
        'matching_chunks_before_edition_filter':before,'related_documents':related[:limit],
        'filters':{'collection':collection,'edition_filter':edition_filter,'path_prefix':path_prefix,
            'match_mode':match_mode,'work_id':work_id},
        'method':'作品归属+表格行/列或作品段落内关键词匹配；不是语义检索',
        'notice':'direct_work_record只证明记录归属；不证明摘要正确，也不把资料转为Canon'}
