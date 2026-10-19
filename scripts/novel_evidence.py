"""General research identities, versioned evidence and project-local observations.

No fetching, model calls, transcript generation or Canon writes happen here.
"""
import difflib
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, model_validator
from novel_store import digest, identifier, now


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Binding(Model):
    kind: Literal['indexed_text', 'reference_book', 'local_file', 'url']
    locator: str = Field(min_length=1, max_length=2000)


class ResearchSource(Model):
    research_source_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    title: str = Field(min_length=1, max_length=200)
    media_type: Literal['text', 'article', 'book', 'video', 'audio', 'pdf']
    resource_type: str = Field(default='', max_length=100)
    source_kind: Literal['primary', 'secondary', 'community', 'user_note', 'unknown'] = 'unknown'
    binding: Binding
    expected_fingerprint: str = Field(default='', pattern=r'^([0-9a-f]{64})?$')
    scope: Literal['global', 'project'] = 'global'
    owner_project: str = Field(default='', max_length=80)
    version_label: str = Field(default='', max_length=200)
    rule_edition: str = Field(default='unknown', max_length=100)

    @model_validator(mode='after')
    def scoped(self):
        if (self.scope == 'project') != bool(self.owner_project):
            raise ValueError('项目私有来源必须指定owner_project；全局来源不能指定owner_project')
        return self


class Position(Model):
    type: Literal['time_range', 'book_range', 'text_range', 'pdf_page', 'web_anchor']
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    chapter_id: str | None = Field(default=None, pattern=r'^[1-9][0-9]*:[1-9][0-9]*$')
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    anchor: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode='after')
    def valid_range(self):
        fields = self.model_dump(exclude_none=True)
        allowed = {
            'time_range': {'type', 'start_ms', 'end_ms'},
            'book_range': {'type', 'chapter_id', 'line_start', 'line_end', 'char_start', 'char_end'},
            'text_range': {'type', 'line_start', 'line_end', 'char_start', 'char_end'},
            'pdf_page': {'type', 'page_start', 'page_end'},
            'web_anchor': {'type', 'anchor'},
        }[self.type]
        if set(fields) - allowed:
            raise ValueError('位置字段与定位类型不匹配')
        for a, b in [('start_ms', 'end_ms'), ('line_start', 'line_end'), ('char_start', 'char_end'), ('page_start', 'page_end')]:
            x, y = getattr(self, a), getattr(self, b)
            if (x is None) != (y is None) or (x is not None and (y < x or (a in ('start_ms', 'char_start') and y == x))):
                raise ValueError('位置范围必须成对且顺序有效')
        required = {'time_range': 'start_ms', 'book_range': 'chapter_id', 'pdf_page': 'page_start', 'web_anchor': 'anchor'}
        if self.type in required and getattr(self, required[self.type]) is None:
            raise ValueError('缺少定位字段')
        if self.type in ('text_range', 'book_range') and self.line_start is None and self.char_start is None:
            raise ValueError('文本位置需要行号或字符范围')
        return self


class Annotation(Model):
    annotation_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    project: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    research_source_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    source_revision: int = Field(ge=1)
    position: Position
    content_type: Literal['original_excerpt', 'original_subtitle', 'sampled_subtitle', 'ai_summary', 'owner_note']
    content: str = Field(min_length=1, max_length=1500)
    observation: str = Field(default='', max_length=3000)
    analysis: str = Field(default='', max_length=6000)
    coverage: Literal['excerpt', 'sample', 'complete_transcript', 'unknown'] = 'unknown'
    limitations: str = Field(min_length=1, max_length=2000)
    open_questions: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    state: Literal['active', 'withdrawn', 'outdated'] = 'active'

    @model_validator(mode='after')
    def bounded_lists(self):
        if any(not x or len(x) > 500 for x in self.open_questions) or any(not x or len(x) > 80 for x in self.tags):
            raise ValueError('标签或待核问题为空或超长')
        if self.content_type == 'sampled_subtitle' and self.coverage != 'sample':
            raise ValueError('抽样字幕必须标记sample，不能称完整转录')
        if self.content_type == 'ai_summary' and self.coverage == 'complete_transcript':
            raise ValueError('AI摘要不能声称完整转录')
        return self


def schema(db):
    db.execute('CREATE TABLE research_sources(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, scope TEXT NOT NULL, owner_project TEXT NOT NULL, binding_key TEXT NOT NULL UNIQUE)')
    db.execute('CREATE TABLE research_source_versions(source_id TEXT NOT NULL REFERENCES research_sources(id), revision INTEGER NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(source_id,revision))')
    db.execute('CREATE TABLE research_project_links(project TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES research_sources(id), revision INTEGER NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(project,source_id,revision))')
    db.execute('CREATE TABLE research_annotation_versions(project TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL, source_id TEXT NOT NULL, source_revision INTEGER NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(project,id,revision), FOREIGN KEY(source_id,source_revision) REFERENCES research_source_versions(source_id,revision))')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class Evidence:
    def __init__(self, workbench, roots=None):
        self.w = workbench
        self.store = workbench.store
        self.roots = [Path(p).resolve() for p in (roots if roots is not None else workbench.research_roots)]

    def file_info(self, locator, media_type):
        path = Path(locator).expanduser()
        extensions = {'book': {'.txt'}, 'text': {'.txt', '.md', '.json', '.csv'}, 'article': {'.txt', '.md'}, 'pdf': {'.pdf'},
                      'video': {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}, 'audio': {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac'}}
        if not path.is_absolute() or path.is_symlink() or path.suffix.lower() not in extensions[media_type]:
            raise ValueError('仅支持许可目录内对应媒介的绝对文件路径；不接受符号链接')
        path = path.resolve()
        if not any(path.is_relative_to(root) for root in self.roots):
            raise ValueError('来源文件不在research_roots许可目录内')
        if not path.is_file():
            raise ValueError('只允许已存在的普通文件')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not __import__('stat').S_ISREG(before.st_mode):
                raise ValueError('只允许普通文件')
            h = hashlib.sha256()
            while data := stream.read(1024 * 1024):
                h.update(data)
            after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns) or path.stat().st_ino != before.st_ino:
            raise ValueError('来源文件在读取期间变化')
        return {'fingerprint': h.hexdigest(), 'fingerprint_scheme': 'sha256_raw_bytes', 'locator': str(path), 'size': before.st_size,
                'processing_status': 'registered_unparsed', 'verification': 'file_bytes_checked'}

    def resolve(self, data):
        binding, media = data['binding'], data['media_type']
        kind, locator = binding['kind'], binding['locator']
        if kind == 'local_file':
            return self.file_info(locator, media)
        if kind == 'indexed_text':
            if media not in ('text', 'article') or not locator.isdigit():
                raise ValueError('indexed_text需旧整数source_id及text/article媒介')
            source = self.store.source(int(locator))
            if not source['current']:
                raise ValueError('旧文本来源不是当前有效版本')
            return {'fingerprint': source['fingerprint'], 'fingerprint_scheme': 'sha256_utf8_decoded_text',
                    'locator': source['path'], 'processing_status': 'indexed_text', 'verification': 'indexed_snapshot',
                    'legacy_source_id': source['id']}
        if kind == 'reference_book':
            if media != 'book':
                raise ValueError('参考书绑定必须为book媒介')
            with self.w.books.opened(locator) as (_, fp, size):
                pass
            index = self.w.books.latest(locator)
            revision = index['revision'] if index and index['fingerprint'] == fp else 0
            return {'fingerprint': fp, 'fingerprint_scheme': 'sha256_raw_bytes', 'locator': str(self.w.books.path(locator)),
                    'size': size, 'index_revision': revision, 'processing_status': 'chapter_indexed' if revision else 'registered_unparsed',
                    'verification': 'file_bytes_checked'}
        url = urlsplit(locator)
        if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password:
            raise ValueError('URL必须是有效HTTP(S)出处且不能带账号密码')
        return {'fingerprint': data['expected_fingerprint'] or None, 'fingerprint_scheme': 'sha256_declared' if data['expected_fingerprint'] else None,
                'locator': locator, 'processing_status': 'registered_unfetched', 'verification': 'declared_unverified'}

    def access(self, db, source_id, project, revision=0):
        source = db.execute('SELECT * FROM research_sources WHERE id=?', (source_id,)).fetchone()
        if not source or (source['scope'] == 'project' and project != source['owner_project']):
            raise ValueError('来源不存在或不属于当前项目')
        selected = revision or source['revision']
        row = db.execute('SELECT body FROM research_source_versions WHERE source_id=? AND revision=?', (source_id, selected)).fetchone()
        if not row:
            raise ValueError('来源版本不存在')
        return dict(source), json.loads(row['body']), selected

    def retry(self, db, namespace, key, request):
        identifier(key)
        row = db.execute('SELECT request,result FROM operations WHERE project=? AND key=?', (namespace, key)).fetchone()
        if row:
            if row['request'] != encode(request):
                raise ValueError('operation_key已用于不同请求')
            return json.loads(row['result'])

    def operation(self, db, namespace, key, request, result):
        db.execute('INSERT INTO operations VALUES(?,?,?,?)', (namespace, key, encode(request), encode(result)))

    def register(self, source, baseline=0, operation_key='', preview_only=True):
        data = ResearchSource.model_validate(source).model_dump(mode='json')
        if baseline < 0:
            raise ValueError('基线不能为负')
        project = data['owner_project']
        if project:
            self.w.project_id(project)
        sid = data['research_source_id']
        request = {'source': data, 'baseline': baseline}
        namespace = 'evidence-source:' + sid
        # Successful exact retries do not require an unchanged external file.
        if not preview_only:
            with self.store.connection() as db:
                previous = self.retry(db, namespace, operation_key, request)
                if previous:
                    return previous
        resolved = self.resolve(data)
        if not preview_only and data['binding']['kind'] != 'url' and data['expected_fingerprint'] != resolved['fingerprint']:
            raise ValueError('保存需预览返回的当前文件/文本指纹')
        if data['expected_fingerprint'] and data['expected_fingerprint'] != resolved['fingerprint']:
            raise ValueError('来源指纹已变化')
        data = {**data, 'expected_fingerprint': ''}  # Do not mutate the idempotency request.
        if data['binding']['kind'] == 'local_file':
            data = {**data, 'binding': {'kind': 'local_file', 'locator': resolved['locator']}}
        elif data['binding']['kind'] == 'indexed_text':
            data = {**data, 'binding': {'kind': 'indexed_text', 'locator': str(resolved['legacy_source_id'])}}
        body = {**data, **resolved, 'canon': False}
        binding_key = encode([data['scope'], project, data['binding']])
        with self.store.connection(write=not preview_only) as db:
            previous = self.retry(db, namespace, operation_key, request) if not preview_only else None
            if previous:
                return previous
            old = db.execute('SELECT * FROM research_sources WHERE id=?', (sid,)).fetchone()
            duplicate = db.execute('SELECT id FROM research_sources WHERE binding_key=? AND id<>?', (binding_key, sid)).fetchone()
            if duplicate:
                raise ValueError('来源已登记：' + duplicate['id'])
            revision = old['revision'] if old else 0
            if old and (old['scope'] != data['scope'] or old['owner_project'] != project or old['binding_key'] != binding_key):
                raise ValueError('来源绑定与范围不能原位更换；请独立登记')
            if revision != baseline:
                raise ValueError('来源版本冲突；重新读取')
            prior = self.access(db, sid, project)[1] if old else {}
            if preview_only:
                return {'saved': False, 'research_source_id': sid, 'baseline': revision, 'source': body, 'fingerprint': resolved['fingerprint'],
                        'diff': self.diff(prior, body), 'canon': False}
            unchanged = prior == body
            new_revision = revision if unchanged else revision + 1
            if not old:
                db.execute('INSERT INTO research_sources VALUES(?,?,?,?,?)', (sid, new_revision, data['scope'], project, binding_key))
            elif not unchanged:
                db.execute('UPDATE research_sources SET revision=? WHERE id=?', (new_revision, sid))
            if not unchanged:
                db.execute('INSERT INTO research_source_versions VALUES(?,?,?,?)', (sid, new_revision, encode(body), now()))
            result = {'research_source_id': sid, 'revision': new_revision, 'fingerprint': resolved['fingerprint'], 'saved': True, 'unchanged': unchanged, 'canon': False}
            self.operation(db, namespace, operation_key, request, result)
            return result

    @staticmethod
    def diff(before, after):
        return '\n'.join(difflib.unified_diff(json.dumps(before, ensure_ascii=False, sort_keys=True, indent=2).splitlines(),
                         json.dumps(after, ensure_ascii=False, sort_keys=True, indent=2).splitlines(), fromfile='current', tofile='proposed', lineterm=''))

    def list_sources(self, project, offset=0, limit=20):
        self.w.project_id(project)
        if offset < 0 or not 1 <= limit <= 50:
            raise ValueError('来源分页范围无效')
        with self.store.connection() as db:
            rows = db.execute("SELECT id,revision FROM research_sources WHERE scope='global' OR owner_project=? ORDER BY id", (project,)).fetchall()
            result = []
            for row in rows[offset:offset+limit]:
                _, body, _ = self.access(db, row['id'], project)
                result.append({'research_source_id': row['id'], 'revision': row['revision'], 'title': body['title'], 'media_type': body['media_type']})
        return {'project': project, 'sources': result, 'total': len(rows), 'next_offset': offset+limit if offset+limit < len(rows) else None, 'canon': False}

    def get(self, source_id, project, revision=0):
        self.w.project_id(project)
        with self.store.connection() as db:
            source, data, selected = self.access(db, source_id, project, revision)
        with self.store.connection() as db:
            link = db.execute('SELECT revision,body FROM research_project_links WHERE project=? AND source_id=? ORDER BY revision DESC LIMIT 1', (project, source_id)).fetchone()
        association = {'revision': link['revision'], **json.loads(link['body'])} if link else None
        state = 'current'
        try:
            current = self.resolve(data)
            if current['fingerprint'] != data['fingerprint'] or current.get('index_revision') != data.get('index_revision'):
                state = 'changed'
            if data['binding']['kind'] == 'url':
                state = 'unverified_remote'
        except (ValueError, OSError):
            state = 'unavailable'
        with self.store.connection() as db:
            stamp = db.execute('SELECT created FROM research_source_versions WHERE source_id=? AND revision=?', (source_id, selected)).fetchone()[0]
        return {'version_fingerprint': digest(encode(data)), 'created_at': stamp, 'research_source_id': source_id, 'revision': selected, 'latest_revision': source['revision'], 'source': data,
                'source_state': state, 'stale': selected != source['revision'] or state in ('changed', 'unavailable'),
                'canon': False, 'project_link': association, 'evidence_reader': self.reader(data)}

    @staticmethod
    def reader(data):
        kind = data['binding']['kind']
        if kind == 'reference_book':
            return {'tool': 'novel_read_book_excerpt', 'book_id': data['binding']['locator'], 'expected_fingerprint': data['fingerprint']}
        if kind == 'indexed_text':
            return {'tool': 'novel_read_source', 'source_id': data['legacy_source_id'], 'fingerprint': data['fingerprint']}
        return {'locator': data['locator'], 'notice': '仅返回文件/URL与位置；本版不播放、解析PDF、抓取网页或转写媒体'}

    def link(self, source_id, project, purpose, tags, active, baseline, operation_key):
        self.w.project_id(project)
        if not isinstance(active, bool) or not purpose.strip() or len(purpose) > 2000 or len(tags) > 20 or any(not isinstance(t, str) or not t or len(t) > 80 for t in tags) or baseline < 0:
            raise ValueError('研究用途、标签或基线无效')
        body = {'purpose': purpose, 'tags': tags, 'active': active}
        namespace = 'evidence-link:' + project + ':' + source_id
        request = {'body': body, 'baseline': baseline}
        with self.store.connection(write=True) as db:
            self.access(db, source_id, project)
            retry = self.retry(db, namespace, operation_key, request)
            if retry:
                return retry
            old = db.execute('SELECT revision,body FROM research_project_links WHERE project=? AND source_id=? ORDER BY revision DESC LIMIT 1', (project, source_id)).fetchone()
            revision = old['revision'] if old else 0
            if baseline != revision:
                raise ValueError('项目关联版本冲突')
            unchanged = old and old['body'] == encode(body)
            new_revision = revision if unchanged else revision + 1
            if not unchanged:
                db.execute('INSERT INTO research_project_links VALUES(?,?,?,?,?)', (project, source_id, new_revision, encode(body), now()))
            result = {'project': project, 'research_source_id': source_id, 'revision': new_revision, **body, 'canon': False}
            self.operation(db, namespace, operation_key, request, result)
            return result

    def validate_annotation(self, data):
        project, sid = data['project'], data['research_source_id']
        self.w.project_id(project)
        source = self.get(sid, project, data['source_revision'])
        if source['stale'] and data['state'] == 'active':
            raise ValueError('证据来源或目录已变化；请核对后登记新版本')
        if data['state'] != 'active':
            with self.store.connection() as db:
                old = db.execute('SELECT body FROM research_annotation_versions WHERE project=? AND id=? ORDER BY revision DESC LIMIT 1', (project, data['annotation_id'])).fetchone()
            if not old:
                raise ValueError('只有已有标注能撤回或标记过时')
            prior = json.loads(old['body'])
            if any(prior[k] != data[k] for k in ('research_source_id', 'source_revision', 'position', 'content_type', 'content', 'coverage')):
                raise ValueError('撤回/过时操作不得更换原证据')
            return {'locator_verification': 'historical_reference', 'content_verification': 'declared_unverified', 'source_state': source['source_state'], 'notice': '保留原证据，标记撤回或过时，不将过期位置套用到新文件'}
        with self.store.connection() as db:
            link = db.execute('SELECT body FROM research_project_links WHERE project=? AND source_id=? ORDER BY revision DESC LIMIT 1', (project, sid)).fetchone()
        if not link or not json.loads(link['body'])['active']:
            raise ValueError('先建立有效的项目研究关联')
        body, position = source['source'], data['position']
        kind, media = body['binding']['kind'], body['media_type']
        typ = position['type']
        expected = 'time_range' if media in ('video', 'audio') else 'pdf_page' if media == 'pdf' else None
        if expected and typ != expected or not expected and typ not in ('book_range', 'text_range', 'web_anchor'):
            raise ValueError('位置类型与媒介不匹配')
        if data['content_type'] in ('original_subtitle', 'sampled_subtitle') and media not in ('video', 'audio'):
            raise ValueError('字幕仅适用于音视频')
        verification = 'declared_unverified'
        if typ == 'book_range':
            if kind != 'reference_book' or not body.get('index_revision'):
                raise ValueError('章节位置需要已建立目录的参考书绑定')
            index, chapter = self.w.books.chapter(body['binding']['locator'], position['chapter_id'], body['fingerprint'])
            if index['revision'] != body['index_revision'] or chapter['kind'] != 'chapter':
                raise ValueError('章节不属于来源绑定的目录版本')
            if position.get('line_start') is not None and not (chapter['line_start'] <= position['line_start'] <= position['line_end'] <= chapter['line_end']):
                raise ValueError('行号超出章节范围')
            from novel_books import lines
            selected_parts, total_chars = [], 0
            with self.w.books.opened(body['binding']['locator'], body['fingerprint']) as (stream, _, __):
                for number, _, _, text in lines(stream, index['encoding'], chapter['byte_start'], chapter['byte_end'], chapter['line_start']):
                    left, right = 0, len(text)
                    if position.get('char_start') is not None:
                        left = max(0, position['char_start'] - total_chars)
                        right = min(len(text), position['char_end'] - total_chars)
                    if position.get('line_start') is not None and not position['line_start'] <= number <= position['line_end']:
                        right = left
                    if right > left and sum(map(len, selected_parts)) < 6000:
                        selected_parts.append(text[left:right][:6000-sum(map(len, selected_parts))])
                    total_chars += len(text)
            if position.get('char_end') is not None and position['char_end'] > total_chars:
                raise ValueError('字符范围超出章节')
            if not selected_parts:
                raise ValueError('行号与字符范围没有共同的章节内容')
            if data['content_type'] == 'original_excerpt' and data['content'] not in ''.join(selected_parts):
                raise ValueError('原文摘录与所选章节片段不一致；定位范围最多核对前6000字符')
            verification = 'chapter_locator_checked'
        elif typ == 'text_range' and kind == 'indexed_text':
            original = self.store.source(body['legacy_source_id'], body['fingerprint'])['body']
            lines = original.splitlines(keepends=True)
            if position.get('line_start') is not None and position['line_end'] > len(lines):
                raise ValueError('行号超出文本范围')
            if position.get('char_start') is not None and position['char_end'] > len(original):
                raise ValueError('字符范围超出文本')
            left, right = 0, len(original)
            if position.get('line_start') is not None:
                left = sum(map(len, lines[:position['line_start']-1]))
                right = sum(map(len, lines[:position['line_end']]))
            if position.get('char_start') is not None:
                left, right = max(left, position['char_start']), min(right, position['char_end'])
            if right <= left:
                raise ValueError('行号与字符范围没有共同的文本内容')
            selected = original[left:right]
            if data['content_type'] == 'original_excerpt' and data['content'] not in selected:
                raise ValueError('原文摘录与所选文本不一致')
            verification = 'text_locator_checked'
        elif typ == 'text_range' and kind not in ('local_file', 'url'):
            raise ValueError('本来源不支持该文本位置')
        elif typ == 'web_anchor' and kind != 'url':
            raise ValueError('网页锚点需要URL绑定')
        return {'locator_verification': verification, 'content_verification': 'declared_unverified', 'source_state': source['source_state'],
                'notice': '位置可追溯不等于观点真实；媒体时间段/PDF页码与字幕由录入者声明，未独立核对'}

    def preview(self, annotation):
        data = Annotation.model_validate(annotation).model_dump(mode='json', exclude_none=True)
        evidence = self.validate_annotation(data)
        with self.store.connection() as db:
            old = db.execute('SELECT revision,body FROM research_annotation_versions WHERE project=? AND id=? ORDER BY revision DESC LIMIT 1', (data['project'], data['annotation_id'])).fetchone()
        prior = json.loads(old['body']) if old else {}
        return {'annotation': data, 'baseline': old['revision'] if old else 0, 'preview_fingerprint': digest(encode(data)),
                'diff': self.diff(prior, data), 'evidence': evidence, 'saved': False, 'canon': False}

    def save(self, annotation, baseline, preview_fingerprint, operation_key):
        data = Annotation.model_validate(annotation).model_dump(mode='json', exclude_none=True)
        self.w.project_id(data['project'])
        namespace = 'evidence-annotation:' + data['project'] + ':' + data['annotation_id']
        request = {'annotation': data, 'baseline': baseline, 'preview_fingerprint': preview_fingerprint}
        with self.store.connection() as db:
            retry = self.retry(db, namespace, operation_key, request)
            if retry:
                return retry
        if preview_fingerprint != digest(encode(data)):
            raise ValueError('标注与预览内容不一致')
        evidence = self.validate_annotation(data)
        with self.store.connection(write=True) as db:
            retry = self.retry(db, namespace, operation_key, request)
            if retry:
                return retry
            source, bound, _ = self.access(db, data['research_source_id'], data['project'], data['source_revision'])
            if data['state'] == 'active':
                fresh = self.resolve(bound)
                if bound['binding']['kind'] != 'url' and (fresh['fingerprint'] != bound['fingerprint'] or fresh.get('index_revision') != bound.get('index_revision')):
                    raise ValueError('来源在标注保存期间变化')
            link = db.execute('SELECT body FROM research_project_links WHERE project=? AND source_id=? ORDER BY revision DESC LIMIT 1', (data['project'], data['research_source_id'])).fetchone()
            if data['state'] == 'active' and (source['revision'] != data['source_revision'] or not link or not json.loads(link['body'])['active']):
                raise ValueError('来源版本或项目关联在保存期间变化')
            old = db.execute('SELECT revision,body FROM research_annotation_versions WHERE project=? AND id=? ORDER BY revision DESC LIMIT 1', (data['project'], data['annotation_id'])).fetchone()
            current = old['revision'] if old else 0
            if baseline != current:
                raise ValueError('标注版本冲突；请重新预览')
            unchanged = old and old['body'] == encode(data)
            revision = current if unchanged else current + 1
            if not unchanged:
                db.execute('INSERT INTO research_annotation_versions VALUES(?,?,?,?,?,?,?)', (data['project'], data['annotation_id'], revision, data['research_source_id'], data['source_revision'], encode(data), now()))
            result = {'project': data['project'], 'annotation_id': data['annotation_id'], 'revision': revision, 'evidence': evidence, 'saved': True, 'canon': False}
            self.operation(db, namespace, operation_key, request, result)
            return result

    def annotations(self, project, source_id='', annotation_id='', revision=0, query='', tag='', offset=0, limit=20):
        self.w.project_id(project)
        if not 1 <= limit <= 50 or offset < 0 or revision < 0 or len(query) > 500:
            raise ValueError('查询范围无效')
        if revision and not annotation_id:
            raise ValueError('历史版本读取必须指定annotation_id')
        with self.store.connection() as db:
            if source_id:
                self.access(db, source_id, project)
            rows = db.execute('SELECT * FROM research_annotation_versions WHERE project=? AND (?="" OR source_id=?) AND (?="" OR id=?) AND ((?=0 AND revision=(SELECT max(revision) FROM research_annotation_versions v WHERE v.project=research_annotation_versions.project AND v.id=research_annotation_versions.id)) OR revision=?) ORDER BY id',
                (project, source_id, source_id, annotation_id, annotation_id, revision, revision)).fetchall()
            hits = []
            for row in rows:
                _, body, _ = self.access(db, row['source_id'], project, row['source_revision'])
                data = json.loads(row['body'])
                if (query and query.casefold() not in encode(data).casefold()) or (tag and tag not in data['tags']):
                    continue
                hits.append({'revision': row['revision'], 'fingerprint': digest(row['body']), 'fingerprint_scheme': 'sha256_canonical_annotation_json', 'annotation': data, 'evidence_reader': self.reader(body), 'canon': False})
        checked = {}
        for hit in hits[offset:offset+limit]:
            key = (hit['annotation']['research_source_id'], hit['annotation']['source_revision'])
            if key not in checked:
                checked[key] = self.get(key[0], project, key[1])
            hit['stale'] = checked[key]['stale']
        return {'project': project, 'total': len(hits), 'annotations': hits[offset:offset+limit], 'next_offset': offset+limit if offset+limit < len(hits) else None,
                'method': '项目范围关键词/标签检索；不是语义检索', 'canon': False}
