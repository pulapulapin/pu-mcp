"""Bounded, read-only TXT access; SQLite stores locators, never book text."""
from __future__ import annotations
import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

PARSER_VERSION = 'zh-txt-1'
CATALOG = {
    'green-dragon-doctor': ('绿龙博士', '绿龙博士.txt'),
    'black-dragon-code': ('黑龙法典', '《黑龙法典》（校对版全本）作者：欢声.txt'),
    'frost-wings': ('霜寒之翼', '霜寒之翼.txt'),
    'green-dragon-nest': ('绿龙筑巢记', '绿龙筑巢记 作者：归兮北冥 1-443.txt'),
}
from novel_config import load_settings
BOOK_ROOT = Path.home() / '.local/share/novel-workbench/books'
NUM = r'[0-9零〇一二三四五六七八九十百千万两]+'
CHAPTER = re.compile(r'^\s*(?:第'+NUM+r'卷[^\r\n]{0,40}?)?(第'+NUM+r'[章节回])([^\r\n]{0,100})\s*$')
VOLUME = re.compile(r'^\s*第'+NUM+r'卷(?:\s+[^\r\n]{1,40})?\s*$')

def schema(db):
    db.execute('''CREATE TABLE reference_indexes(book_id TEXT NOT NULL, revision INTEGER NOT NULL,
        work_id TEXT NOT NULL, path TEXT NOT NULL, fingerprint TEXT NOT NULL, encoding TEXT NOT NULL,
        parser_version TEXT NOT NULL, size INTEGER NOT NULL, warnings TEXT NOT NULL,
        corrections TEXT NOT NULL, PRIMARY KEY(book_id,revision))''')
    db.execute('''CREATE TABLE reference_chapters(book_id TEXT NOT NULL, revision INTEGER NOT NULL,
        ordinal INTEGER NOT NULL, title TEXT NOT NULL, printed_number TEXT NOT NULL, kind TEXT NOT NULL,
        byte_start INTEGER NOT NULL, byte_end INTEGER NOT NULL, line_start INTEGER NOT NULL,
        line_end INTEGER NOT NULL, PRIMARY KEY(book_id,revision,ordinal),
        FOREIGN KEY(book_id,revision) REFERENCES reference_indexes(book_id,revision))''')

def signature(stream):
    st = os.fstat(stream.fileno())
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

def fingerprint(stream):
    stream.seek(0)
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(block)
    stream.seek(0)
    return h.hexdigest()

def lines(stream, encoding, start=0, end=None, first_line=1):
    stream.seek(start)
    number = first_line
    while end is None or stream.tell() < end:
        pos = stream.tell()
        raw = stream.readline(131073)
        if not raw:
            break
        if len(raw) > 131072:
            raise ValueError('单行超过128KiB，请先提供可分行的TXT副本；原文件未修改')
        text = raw.decode('utf-8' if encoding == 'utf-8-sig' else encoding, errors='strict')
        if pos == 0:
            text = text.lstrip('\ufeff')
        yield number, pos, raw, text
        number += 1

class Books:
    def __init__(self, store, root=None, catalog=None):
        self.store = store
        self.root = Path(root or load_settings()['books_root']).resolve()
        self.fixed_catalog = catalog

    @property
    def catalog(self):
        if self.fixed_catalog is not None:return self.fixed_catalog
        result=dict(CATALOG)
        with self.store.connection() as db:
            rows=db.execute('SELECT * FROM reference_registry r WHERE revision=(SELECT max(revision) FROM reference_registry WHERE book_id=r.book_id)').fetchall()
        result.update({row['book_id']:(row['title'],row['relative_path']) for row in rows})
        return result

    def registry(self,book_id):
        with self.store.connection() as db:
            row=db.execute('SELECT * FROM reference_registry WHERE book_id=? ORDER BY revision DESC LIMIT 1',(book_id,)).fetchone()
        return dict(row) if row else {'revision':0,'active':1}

    def path(self, book_id, allow_inactive=False):
        if book_id not in self.catalog:
            raise ValueError('只允许已配置的参考小说ID；先列出参考小说')
        if self.fixed_catalog is None and not allow_inactive and not self.registry(book_id)['active']:raise ValueError('作品已停用；需显式启用后读取')
        path = self.root / self.catalog[book_id][1]
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError('拒绝符号链接或目录外文件')
        return path

    @contextmanager
    def opened(self, book_id, expected=''):
        path = self.path(book_id)
        # O_NOFOLLOW also closes the check/open symlink race on macOS/Linux.
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            before = signature(stream)
            fp = fingerprint(stream)
            if expected and fp != expected:
                raise ValueError('参考小说已变化，索引失效；请重新列出并建立索引')
            yield stream, fp, before[2]
            if signature(stream) != before or path.stat().st_ino != before[1]:
                raise ValueError('读取期间原文件发生变化；本次结果作废')

    def latest(self, book_id, revision=0):
        with self.store.connection() as db:
            row = db.execute('''SELECT * FROM reference_indexes WHERE book_id=?
                AND (?=0 OR revision=?) ORDER BY revision DESC LIMIT 1''',
                (book_id, revision, revision)).fetchone()
        return dict(row) if row else None

    def list(self):
        result = []
        for book_id, (title, _) in self.catalog.items():
            row = {'book_id': book_id, 'work_id': book_id, 'title': title, 'path': str(self.path(book_id,True)), 'active':bool(self.registry(book_id)['active']), 'registry_revision':self.registry(book_id)['revision']}
            old = self.latest(book_id)
            if not row['active']:
                row.update(available=False,index_revision=old['revision'] if old else 0);result.append(row);continue
            try:
                with self.opened(book_id) as (_, fp, size):
                    row.update(available=True, fingerprint=fp, fingerprint_scheme='sha256-raw-bytes', size=size,
                        index_revision=old['revision'] if old else 0,
                        index_state='current' if old and fp == old['fingerprint'] else 'stale' if old else 'not_indexed')
            except OSError:
                row.update(available=False, index_state='missing', index_revision=old['revision'] if old else 0)
            result.append(row)
        return {'books': result, 'policy': '参考小说不是项目正文；仅保存目录和位置，完整性未核验'}

    def index(self, book_id, expected_fingerprint, baseline=0, corrections=None):
        if not re.fullmatch('[0-9a-f]{64}', expected_fingerprint):
            raise ValueError('必须传列表返回的原文件SHA-256')
        corrections = corrections or []
        if len(corrections) > 500:
            raise ValueError('一次最多修正500个目录位置')
        manual = {}
        for item in corrections:
            if (not isinstance(item, dict) or set(item) - {'line', 'title', 'kind'} or
                    type(item.get('line')) is not int or item['line'] < 1 or
                    item.get('kind') not in {'chapter', 'volume', 'ignore'} or
                    not isinstance(item.get('title', ''), str) or len(item.get('title', '')) > 120):
                raise ValueError('目录修正需要line正整数、kind=chapter/volume/ignore和有限title')
            if item['line'] in manual:
                raise ValueError('同一行不能重复修正')
            manual[item['line']] = item
        headings, warnings = [], []
        with self.opened(book_id, expected_fingerprint) as (stream, fp, size):
            initial_signature = signature(stream)
            for encoding in ('utf-8-sig', 'gb18030'):
                try:
                    headings, total_lines = [], 0
                    for number, offset, raw, text in lines(stream, encoding):
                        total_lines = number
                        title = text.strip()
                        m = CHAPTER.fullmatch(title)
                        kind = 'chapter' if m else 'volume' if VOLUME.fullmatch(title) else ''
                        label = m.group(1) if m else ''
                        if number in manual:
                            edit = manual[number]
                            kind = '' if edit['kind'] == 'ignore' else edit['kind']
                            title = edit.get('title') or title
                        if kind:
                            headings.append([title, label, kind, offset, number, False])
                            if len(headings) > 20000:
                                raise ValueError('目录超过20000项，需检查章节格式')
                        elif headings and title:
                            headings[-1][5] = True
                    break
                except UnicodeDecodeError:
                    if encoding == 'gb18030':
                        raise ValueError('TXT无法严格解码为UTF-8或GB18030，不替换乱码')
            if any(n > total_lines for n in manual):
                raise ValueError('修正行号超出文件范围')
            # A run of adjacent headings is probably a table of contents, not repeated body chapters.
            toc_ordinals = set()
            for i in range(len(headings)-2):
                if (all(h[2]=='chapter' for h in headings[i:i+3]) and
                        not any(h[5] for h in headings[i:i+2]) and headings[i+2][4]-headings[i][4] <= 4):
                    toc_ordinals.update((i,i+1,i+2))
            for i in toc_ordinals:
                if headings[i][4] not in manual:
                    headings[i][2] = 'contents'
            labels = [h[1] for h in headings if h[2] == 'chapter' and h[1]]
            if len(labels) != len(set(labels)):
                warnings.append('存在重复章节编号；使用chapter_id定位，不按编号自动去重')
            if any(h[2] == 'contents' for h in headings):
                warnings.append('检测到疑似目录条目；自动识别仍需核对，可按行修正')
            warnings.append('章节结构为自动识别，不证明作品完整或章节无遗漏')
            entries = []
            for i, (title, label, kind, start, line, has_body) in enumerate(headings):
                end = headings[i+1][3] if i+1 < len(headings) else size
                last = headings[i+1][4]-1 if i+1 < len(headings) else total_lines
                entries.append((i+1, title, label, kind, start, end, line, last))
            if signature(stream) != initial_signature or self.path(book_id).stat().st_ino != initial_signature[1]:
                raise ValueError('索引期间原文件发生变化；没有保存目录')
            with self.store.connection(write=True) as db:
                old = db.execute('SELECT * FROM reference_indexes WHERE book_id=? ORDER BY revision DESC LIMIT 1', (book_id,)).fetchone()
                current = old['revision'] if old else 0
                request = json.dumps(corrections, ensure_ascii=False, sort_keys=True)
                if old and old['fingerprint'] == fp and old['corrections'] == request and old['parser_version'] == PARSER_VERSION:
                    # Retry is idempotent only for the same content and its immediate baseline.
                    if baseline not in (current, current-1):
                        raise ValueError('目录版本冲突，请重新读取')
                    return {'book_id': book_id, 'revision': current, 'fingerprint': fp, 'unchanged': True}
                if baseline != current:
                    raise ValueError('目录版本冲突，请重新读取')
                rev = current+1
                db.execute('INSERT INTO reference_indexes VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (book_id, rev, book_id, str(self.path(book_id)), fp, encoding, PARSER_VERSION,
                     size, json.dumps(warnings, ensure_ascii=False), request))
                db.executemany('INSERT INTO reference_chapters VALUES(?,?,?,?,?,?,?,?,?,?)',
                    [(book_id, rev, *entry) for entry in entries])
        return {'book_id': book_id, 'revision': rev, 'fingerprint': fp, 'encoding': encoding,
            'chapter_count': sum(e[3] == 'chapter' for e in entries), 'warnings': warnings, 'original_modified': False}

    def structure(self, book_id, offset=0, limit=50, revision=0):
        if type(offset) is not int or offset < 0 or not 1 <= limit <= 200:
            raise ValueError('目录分页offset需非负，limit为1–200')
        index = self.latest(book_id, revision)
        if not index:
            raise ValueError('参考小说尚未建立索引')
        with self.opened(book_id, index['fingerprint']):
            with self.store.connection() as db:
                total = db.execute('SELECT count(*) FROM reference_chapters WHERE book_id=? AND revision=?', (book_id,index['revision'])).fetchone()[0]
                rows = db.execute('SELECT * FROM reference_chapters WHERE book_id=? AND revision=? ORDER BY ordinal LIMIT ? OFFSET ?',
                    (book_id,index['revision'],limit,offset)).fetchall()
        return {'book_id': book_id, 'work_id': book_id, 'revision': index['revision'],
            'fingerprint': index['fingerprint'], 'fingerprint_scheme': 'sha256-raw-bytes', 'encoding': index['encoding'],
            'warnings': json.loads(index['warnings']), 'total_entries': total,
            'entries': [dict(r, chapter_id=f"{index['revision']}:{r['ordinal']}") for r in rows],
            'next_offset': offset+len(rows) if offset+len(rows)<total else None}

    def chapter(self, book_id, chapter_id, expected_fingerprint):
        if not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*', chapter_id):
            raise ValueError('chapter_id需要目录返回的版本:序号')
        rev, ordinal = map(int, chapter_id.split(':'))
        index = self.latest(book_id, rev)
        if not index or index['fingerprint'] != expected_fingerprint:
            raise ValueError('目录版本或原文件指纹不匹配')
        with self.store.connection() as db:
            row = db.execute('SELECT * FROM reference_chapters WHERE book_id=? AND revision=? AND ordinal=?', (book_id,rev,ordinal)).fetchone()
        if not row or row['kind'] != 'chapter':
            raise ValueError('该位置不是可读取的正文章节')
        return index, dict(row)

    def read(self, book_id, chapter_id, expected_fingerprint, char_offset=0, max_chars=3000):
        if type(char_offset) is not int or not 0 <= char_offset <= 1000000 or not 1 <= max_chars <= 6000:
            raise ValueError('片段offset需0–1000000，max_chars需1–6000')
        index, chapter = self.chapter(book_id, chapter_id, expected_fingerprint)
        parts, skipped, used, start, end, first, last, more = [], 0, 0, None, None, None, None, False
        with self.opened(book_id, expected_fingerprint) as (stream, _, __):
            for number, pos, raw, text in lines(stream, index['encoding'], chapter['byte_start'], chapter['byte_end'], chapter['line_start']):
                if skipped+len(text) <= char_offset:
                    skipped += len(text)
                    continue
                cut = max(0, char_offset-skipped)
                take = min(len(text)-cut, max_chars-used)
                if take:
                    prefix_bytes = len(text[:cut].encode(index['encoding'].replace('-sig','')))
                    if pos == 0 and raw.startswith(b'\xef\xbb\xbf'):
                        prefix_bytes += 3
                    if start is None:
                        start, first = pos+prefix_bytes, number
                    parts.append(text[cut:cut+take])
                    end, last = pos+prefix_bytes+len(text[cut:cut+take].encode(index['encoding'].replace('-sig',''))), number
                    used += take
                skipped += len(text)
                if used == max_chars:
                    more = cut+take < len(text) or stream.tell() < chapter['byte_end']
                    break
        return {'book_id': book_id, 'work_id': book_id, 'chapter_id': chapter_id, 'title': chapter['title'],
            'fingerprint': expected_fingerprint, 'fingerprint_scheme': 'sha256-raw-bytes',
            'body': ''.join(parts), 'line_start': first, 'line_end': last, 'byte_start': start, 'byte_end': end,
            'char_offset': char_offset, 'truncated': more, 'next_char_offset': char_offset+used if more else None,
            'evidence_type': 'primary_text', 'source_kind': 'reference_novel', 'canon': False}

    def search(self, book_id, query, expected_fingerprint, limit=10, start_ordinal=1, max_chapters=50):
        if not isinstance(query, str) or not query.strip() or len(query)>100 or not 1 <= limit <= 20 or not 1 <= max_chapters <= 100 or start_ordinal<1:
            raise ValueError('需要有限关键词；limit1–20，max_chapters1–100，start_ordinal正整数')
        index = self.latest(book_id)
        if not index or index['fingerprint'] != expected_fingerprint:
            raise ValueError('当前目录与指纹不匹配，请重新索引')
        with self.store.connection() as db:
            chapters = db.execute('SELECT * FROM reference_chapters WHERE book_id=? AND revision=? AND ordinal>=? AND kind=? ORDER BY ordinal LIMIT ?',
                (book_id,index['revision'],start_ordinal,'chapter',max_chapters+1)).fetchall()
        hits, scanned, next_ordinal, early = [], [], None, False
        with self.opened(book_id, expected_fingerprint) as (stream, _, __):
            for chapter in chapters[:max_chapters]:
                scanned.append(chapter['ordinal'])
                chapter_chars = 0
                for number, pos, raw, text in lines(stream,index['encoding'],chapter['byte_start'],chapter['byte_end'],chapter['line_start']):
                    match = re.search(re.escape(query),text,re.IGNORECASE)
                    if match:
                        at = match.start()
                        hits.append({'chapter_id': f"{index['revision']}:{chapter['ordinal']}", 'title': chapter['title'],
                            'line_start': number, 'line_end': number, 'byte_start': pos, 'byte_end': pos+len(raw),
                            'char_offset': chapter_chars+max(0, at-60), 'excerpt': text[max(0,at-60):at+len(query)+120],
                            'fingerprint': expected_fingerprint, 'work_id': book_id, 'evidence_type': 'primary_text'})
                        # One hit per chapter keeps results useful and continuation unambiguous.
                        break
                    chapter_chars += len(text)
                if len(hits) == limit:
                    next_ordinal, early = chapter['ordinal']+1, True
                    break
            if not early and len(chapters)>max_chapters:
                next_ordinal = chapters[max_chapters]['ordinal']
        return {'book_id': book_id, 'query': query, 'hits': hits, 'scanned_ordinals': scanned,
            'next_start_ordinal': next_ordinal, 'complete': next_ordinal is None,
            'method': '指定作品逐行字面匹配，每章节最多返回一处；不是语义检索', 'canon': False}
