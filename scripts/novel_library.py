"""Versioned catalog, declared source metadata and reported reading progress."""
import hashlib
import json
import re
from novel_research import EDITIONS

KINDS=('novel','game','rulebook','research_summary','research_card')

def schema(db):
    db.execute('CREATE TABLE reference_registry(book_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL, relative_path TEXT NOT NULL, active INTEGER NOT NULL, fingerprint TEXT NOT NULL, PRIMARY KEY(book_id,revision))')
    db.execute('CREATE TABLE source_metadata(source_id INTEGER NOT NULL, fingerprint TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(source_id,fingerprint,revision), FOREIGN KEY(source_id,fingerprint) REFERENCES source_versions(source_id,fingerprint))')
    db.execute('CREATE TABLE reading_progress(book_id TEXT NOT NULL, revision INTEGER NOT NULL, fingerprint TEXT NOT NULL, index_revision INTEGER NOT NULL, entries TEXT NOT NULL, summary TEXT NOT NULL, operation_key TEXT NOT NULL, request TEXT NOT NULL, PRIMARY KEY(book_id,revision), UNIQUE(book_id,operation_key))')

def metadata(store,source_id,fingerprint=''):
    with store.connection() as db:
        source=db.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone()
        if source is None:raise ValueError('来源不存在')
        fp=fingerprint or source['fingerprint']
        if not db.execute('SELECT 1 FROM source_versions WHERE source_id=? AND fingerprint=?',(source_id,fp)).fetchone():raise ValueError('来源版本不存在')
        row=db.execute('SELECT * FROM source_metadata WHERE source_id=? AND fingerprint=? ORDER BY revision DESC LIMIT 1',(source_id,fp)).fetchone()
    return {'source_id':source_id,'fingerprint':fp,'current':fp==source['fingerprint'],'revision':row['revision'] if row else 0,
            'metadata':json.loads(row['body']) if row else None,'verification':'declared_unverified','canon':False}

def set_metadata(store,source_id,fingerprint,source_kind,work_title,rule_edition,source_locator,notes,baseline,retrieved_on=""):
    if retrieved_on:
        from datetime import date
        date.fromisoformat(retrieved_on)
    if source_kind not in KINDS or rule_edition not in EDITIONS or rule_edition=='all':raise ValueError('来源类型或版本声明无效')
    if any(not isinstance(s,str) or len(s)>1000 for s in (work_title,source_locator,notes)) or not source_locator.strip():raise ValueError('需要有限文本与明确来源定位，不能只按游戏名推定版本')
    body=json.dumps({'source_kind':source_kind,'work_title':work_title,'rule_edition':rule_edition,'source_locator':source_locator,'notes':notes,'retrieved_on':retrieved_on},ensure_ascii=False,sort_keys=True)
    with store.connection(write=True) as db:
        source=db.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone()
        if source is None or source['fingerprint']!=fingerprint:raise ValueError('来源指纹已变化；重新读取后再声明')
        row=db.execute('SELECT * FROM source_metadata WHERE source_id=? AND fingerprint=? ORDER BY revision DESC LIMIT 1',(source_id,fingerprint)).fetchone()
        current=row['revision'] if row else 0
        if row and row['body']==body and baseline in (current,current-1):return {'revision':current,'unchanged':True,'verification':'declared_unverified'}
        if baseline!=current:raise ValueError('来源元数据版本冲突')
        db.execute('INSERT INTO source_metadata VALUES(?,?,?,?)',(source_id,fingerprint,current+1,body))
    return metadata(store,source_id,fingerprint)

def annotated_reference(store,source_id,fingerprint,reference):
    info=metadata(store,source_id,fingerprint)
    result={**reference,'source_metadata':info}
    # A declaration is an additional filter cue, never a replacement for excerpt evidence.
    declared=(info['metadata'] or {}).get('rule_edition','unknown')
    if declared=='mixed':
        result.update(edition_scope='mixed',edition_evidence=reference['edition_evidence']+[{'edition':'mixed','basis':'source_declaration_unverified','marker':info['metadata']['source_locator']}])
    if declared not in ('unknown','mixed'):
        refs=list(dict.fromkeys(reference['edition_refs']+[declared]))
        result.update(edition_refs=refs,edition_scope='mixed' if len(refs)>1 else refs[0],
            edition_evidence=reference['edition_evidence']+[{'edition':declared,'basis':'source_declaration_unverified','marker':info['metadata']['source_locator']}])
    return result

def register(books,book_id,title,relative_path,expected_fingerprint,baseline,active=True):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',book_id) or not isinstance(title,str) or not title.strip() or len(title)>200:raise ValueError('作品ID或书名无效')
    from pathlib import Path
    p=Path(relative_path)
    if p.is_absolute() or '..' in p.parts or p.suffix.lower()!='.txt' or '\\' in relative_path:raise ValueError('仅允许books_root内的相对TXT路径')
    from novel_books import Books
    if not re.fullmatch(r'[0-9a-f]{64}',expected_fingerprint):raise ValueError('需要有效原文件SHA256')
    temporary=Books(books.store,books.root,{book_id:(title,relative_path)})
    with temporary.opened(book_id,expected_fingerprint) as (_,fp,_):
        if not expected_fingerprint or fp!=expected_fingerprint:raise ValueError('注册需要原文件SHA256')
    with books.store.connection(write=True) as db:
        row=db.execute('SELECT * FROM reference_registry WHERE book_id=? ORDER BY revision DESC LIMIT 1',(book_id,)).fetchone()
        current=row['revision'] if row else 0
        if row and row['relative_path']!=relative_path:raise ValueError('book_id不能重新指向另一原著')
        # Existing indexes bind the identity to its original file. Registering cannot retarget it.
        indexed=db.execute('SELECT path FROM reference_indexes WHERE book_id=? ORDER BY revision DESC LIMIT 1',(book_id,)).fetchone()
        if indexed and Path(indexed['path']).resolve()!=temporary.path(book_id).resolve():raise ValueError('已有目录的book_id不能指向另一原著')
        for other,(other_title,other_path) in books.catalog.items():
            if other!=book_id and (books.root/other_path).resolve()==temporary.path(book_id).resolve():raise ValueError('同一原著已使用另一book_id注册')
        values=(title,relative_path,int(active),fp)
        if row and tuple(row[k] for k in ('title','relative_path','active','fingerprint'))==values and baseline in (current,current-1):return {'book_id':book_id,'revision':current,'unchanged':True}
        if baseline!=current:raise ValueError('书目版本冲突')
        db.execute('INSERT INTO reference_registry VALUES(?,?,?,?,?,?)',(book_id,current+1,*values))
    return {'book_id':book_id,'revision':current+1,'fingerprint':fp,'active':active,'indexed':False,'notice':'书目已登记；使用既有索引接口建立章节目录，原文未复制'}

def set_active(books,book_id,active,baseline):
    if type(active) is not bool:raise ValueError('active必须是布尔值')
    if book_id not in books.catalog:raise ValueError('作品不存在')
    with books.store.connection(write=True) as db:
        old=db.execute('SELECT * FROM reference_registry WHERE book_id=? ORDER BY revision DESC LIMIT 1',(book_id,)).fetchone()
        current=old['revision'] if old else 0
        if baseline!=current:raise ValueError('书目版本冲突')
        if old and bool(old['active'])==active:return {'book_id':book_id,'revision':current,'unchanged':True}
        title,path=books.catalog[book_id]
        db.execute('INSERT INTO reference_registry VALUES(?,?,?,?,?,?)',(book_id,current+1,title,path,int(active),old['fingerprint'] if old else ''))
    return {'book_id':book_id,'revision':current+1,'active':active,'notice':'只改变书目状态，不删除文件、目录或阅读记录'}

def progress(books,book_id,offset=0,limit=100):
    if type(offset) is not int or offset<0 or not 1<=limit<=200:raise ValueError("进度分页offset非负，limit1–200")
    if book_id not in books.catalog:raise ValueError('作品不存在')
    index=books.latest(book_id)
    with books.store.connection() as db:
        row=db.execute('SELECT * FROM reading_progress WHERE book_id=? ORDER BY revision DESC LIMIT 1',(book_id,)).fetchone()
        chapters=db.execute("SELECT ordinal,title FROM reference_chapters WHERE book_id=? AND revision=? AND kind='chapter' ORDER BY ordinal",(book_id,index['revision'] if index else 0)).fetchall()
    entries=json.loads(row['entries']) if row else {}
    stale=bool(row and (not index or row['fingerprint']!=index['fingerprint'] or row['index_revision']!=index['revision']))
    source_state='not_checked'
    try:
        with books.opened(book_id, index['fingerprint'] if index else ''):source_state='current'
    except (OSError,ValueError):source_state='unavailable_or_changed';stale=bool(row)
    statuses=[];continuous=[];still_continuous=True
    for chapter in chapters:
        cid=f"{index['revision']}:{chapter['ordinal']}"
        modes=entries.get(cid,[]) if not stale else []
        mode='complete' if 'complete' in modes else 'sampled' if 'sampled' in modes else 'keyword_hit' if 'keyword_hit' in modes else 'not_recorded'
        statuses.append({'chapter_id':cid,'title':chapter['title'],'status':mode,'reported_modes':modes})
        if mode=='complete' and still_continuous:continuous.append(cid)
        else:still_continuous=False
    return {'book_id':book_id,'revision':row['revision'] if row else 0,'fingerprint':row['fingerprint'] if row else None,
            'index_revision':row['index_revision'] if row else None,'stale':stale,'source_state':source_state,
            'summary':row['summary'] if row else '', 'entries':statuses[offset:offset+limit],'total_chapters':len(statuses),
            'next_offset':offset+limit if offset+limit<len(statuses) else None,
            'historical_reported_entries':dict(list(entries.items())[offset:offset+limit]) if stale else {},
            'continuous_complete_chapter_ids':continuous[:200],
            'continuous_complete':{'first':continuous[0] if continuous else None,'last':continuous[-1] if continuous else None,'count':len(continuous)},'verification':'reported_not_independently_verified',
            'notice':'完整阅读为调用方明确记录，不是模型已理解或全书已读的证明；not_recorded表示无记录。指纹/目录变化后旧进度不可直接套用。'}

def record_progress(books,book_id,chapter_ids,fingerprint,mode,summary,baseline,operation_key):
    if mode not in ('complete','sampled','keyword_hit') or not isinstance(chapter_ids,list) or not 1<=len(chapter_ids)<=200:raise ValueError('阅读类型无效或章节数不在1–200')
    if not isinstance(summary,str) or len(summary)>1000 or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',operation_key):raise ValueError('摘要或operation_key无效')
    index=books.latest(book_id)
    if not index or index['fingerprint']!=fingerprint:raise ValueError('请先建立当前原文的目录')
    with books.opened(book_id,fingerprint):pass
    for cid in chapter_ids:
        matched,chapter=books.chapter(book_id,cid,fingerprint)
        if matched['revision']!=index['revision']:raise ValueError('阅读记录只能使用当前目录chapter_id')
    request=json.dumps([sorted(set(chapter_ids)),fingerprint,mode,summary],ensure_ascii=False)
    with books.store.connection(write=True) as db:
        retry=db.execute('SELECT * FROM reading_progress WHERE book_id=? AND operation_key=?',(book_id,operation_key)).fetchone()
        if retry:
            if retry['request']!=request:raise ValueError('operation_key已用于另一阅读记录')
            return {'book_id':book_id,'revision':retry['revision'],'reused':True}
        latest=db.execute('SELECT revision FROM reference_indexes WHERE book_id=? ORDER BY revision DESC LIMIT 1',(book_id,)).fetchone()
        if latest['revision']!=index['revision']:raise ValueError('目录在记录期间发生变化，请重新读取')
        old=db.execute('SELECT * FROM reading_progress WHERE book_id=? ORDER BY revision DESC LIMIT 1',(book_id,)).fetchone()
        current=old['revision'] if old else 0
        if baseline!=current:raise ValueError('阅读进度版本冲突')
        entries=json.loads(old['entries']) if old and old['fingerprint']==fingerprint and old['index_revision']==index['revision'] else {}
        for cid in set(chapter_ids):entries[cid]=sorted(set(entries.get(cid,[])+[mode]))
        db.execute('INSERT INTO reading_progress VALUES(?,?,?,?,?,?,?,?)',(book_id,current+1,fingerprint,index['revision'],json.dumps(entries),summary,operation_key,request))
    return {'book_id':book_id,'revision':current+1,'verification':'reported_not_independently_verified','canon':False}


def progress_summary(books):
    with books.store.connection() as db:
        rows=db.execute('SELECT * FROM reading_progress r WHERE revision=(SELECT max(revision) FROM reading_progress WHERE book_id=r.book_id) ORDER BY book_id LIMIT 100').fetchall()
    result=[]
    for row in rows:
        index=books.latest(row['book_id']);entries=json.loads(row['entries'])
        result.append({'book_id':row['book_id'],'revision':row['revision'],'summary':row['summary'],
            'stale_index':not index or index['revision']!=row['index_revision'] or index['fingerprint']!=row['fingerprint'],
            'reported_complete':sum('complete' in modes for modes in entries.values()),
            'reported_sampled':sum('sampled' in modes for modes in entries.values()),
            'reported_keyword_hits':sum('keyword_hit' in modes for modes in entries.values()),
            'notice':'摘要未重新核对原文件；使用novel_get_reading_progress获取当前来源状态'})
    return result

def inspect_file(books,relative_path):
    from pathlib import Path
    from novel_books import Books
    p=Path(relative_path)
    if p.is_absolute() or '..' in p.parts or p.suffix.lower()!='.txt' or '\\' in relative_path:raise ValueError('只允许books_root内相对TXT路径')
    temporary=Books(books.store,books.root,{'inspect':(p.stem,relative_path)})
    with temporary.opened('inspect') as (_,fp,size):return {'relative_path':relative_path,'suggested_title':p.stem,'fingerprint':fp,'size':size,'registered':False}
