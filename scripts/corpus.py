"""Neutral, rebuildable text-corpus projection over configured collections."""
from __future__ import annotations

import json
import re
from pathlib import Path

from novel_config import load_settings
from novel_store import LEGACY_CARD_COLLECTION, Store, digest, identifier


TEXT_SUFFIXES = {'.md', '.txt', '.json'}
MAX_FILE_BYTES = 2_000_000


def _filters(path_prefix: str, match_mode: str) -> None:
    if match_mode not in ('any', 'all'):
        raise ValueError('match_mode必须为any或all')
    if (not isinstance(path_prefix, str) or len(path_prefix) > 256
            or path_prefix.startswith('/') or '\\' in path_prefix or '\x00' in path_prefix
            or any(part in ('.', '..') for part in path_prefix.split('/'))):
        raise ValueError('path_prefix必须为集合内相对路径前缀，不能包含目录穿越')


class Corpus:
    def __init__(self, settings=None):
        self.settings = settings or load_settings(neutral=True)
        self.store = Store(self.settings['data_dir'])
        self.collections = self.settings.get('collections', {})

    def _root(self, collection: str) -> Path:
        identifier(collection)
        if collection == LEGACY_CARD_COLLECTION:
            raise ValueError('旧研究卡不是corpus目录集合，请使用历史兼容读取或迁移为知识记录')
        root = self.collections.get(collection)
        if root is None:
            raise ValueError('资料集合未配置；只允许预先配置的目录')
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError('资料集合目录不存在')
        return root

    def list(self) -> dict:
        return {
            'collections': [
                {'id': key, 'available': Path(value).is_dir()}
                for key, value in sorted(self.collections.items())
                if key != LEGACY_CARD_COLLECTION
            ],
            'projection': 'rebuildable',
            'source_of_truth': 'configured files',
        }

    def _manifest(self, collection: str) -> dict:
        root = self._root(collection)
        files, skipped = [], []
        for path in sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                skipped.append({'path': rel, 'reason': '符号链接或目录外文件'})
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                skipped.append({'path': rel, 'reason': '超过2MB；需拆分后导入'})
                continue
            try:
                body = path.read_text(encoding='utf-8-sig')
            except (UnicodeError, OSError) as exc:
                skipped.append({'path': rel, 'reason': type(exc).__name__})
                continue
            files.append({'path': rel, 'fingerprint': digest(body), 'characters': len(body)})
        return {'collection': collection, 'files': files, 'skipped': skipped}

    def preview_index(self, collection: str) -> dict:
        manifest = self._manifest(collection)
        with self.store.connection() as db:
            rows = [dict(row) for row in db.execute(
                'SELECT path,fingerprint,active FROM sources WHERE collection=? ORDER BY path',
                (collection,),
            )]
        current = {row['path']: row for row in rows}
        seen = {item['path'] for item in manifest['files']}
        changes = []
        for item in manifest['files']:
            old = current.get(item['path'])
            action = 'unchanged' if old and old['fingerprint'] == item['fingerprint'] and old['active'] else 'update' if old else 'add'
            changes.append({**item, 'action': action})
        changes.extend(
            {'path': row['path'], 'fingerprint': row['fingerprint'], 'action': 'deactivate'}
            for row in rows if row['active'] and row['path'] not in seen
        )
        baseline = [{'path': row['path'], 'fingerprint': row['fingerprint'], 'active': bool(row['active'])} for row in rows]
        preview_fingerprint = digest(json.dumps(
            {'manifest': manifest, 'baseline': baseline},
            ensure_ascii=False, sort_keys=True, separators=(',', ':'),
        ))
        return {
            'collection': collection,
            'changes': changes,
            'skipped': manifest['skipped'],
            'preview_fingerprint': preview_fingerprint,
            'saved': False,
            'notice': '仅预览可重建检索投影；不修改原文件、来源证据、任务或项目事实。',
        }

    def commit_index(self, collection: str, preview_fingerprint: str) -> dict:
        if not re.fullmatch(r'[0-9a-f]{64}', preview_fingerprint or ''):
            raise ValueError('preview_fingerprint必须为预览返回的SHA-256')
        preview = self.preview_index(collection)
        if preview['preview_fingerprint'] != preview_fingerprint:
            raise ValueError('集合文件或索引基线已变化；请重新预览')
        manifest = self._manifest(collection)
        preview_files = [
            {key: item[key] for key in ('path', 'fingerprint', 'characters')}
            for item in preview['changes'] if item['action'] != 'deactivate'
        ]
        if manifest['files'] != preview_files or manifest['skipped'] != preview['skipped']:
            raise ValueError('集合文件已在预览后变化；请重新预览')
        result = self.store.index(
            collection,
            self._root(collection),
            classifier=None,
            expected_manifest=manifest['files'],
        )
        return {
            **result,
            'preview_fingerprint': preview_fingerprint,
            'saved': True,
            'classification': 'unclassified',
            'notice': '索引是可重建检索投影；不修改原文件，不产生已验证事实或Canon。',
        }

    def search(self, query: str, limit: int = 6, collection: str = '', path_prefix: str = '', match_mode: str = 'any') -> dict:
        _filters(path_prefix, match_mode)
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            raise ValueError('查询必须为1–500字文本')
        if not 1 <= limit <= 20:
            raise ValueError('limit必须在1–20之间')
        if collection:
            self._root(collection)
        terms = list(dict.fromkeys(re.findall(r'[^\s,，。；;？?、]+', query.lower())))[:12]
        if not terms:
            raise ValueError('查询需要至少一个有效关键词')
        joiner = ' AND ' if match_mode == 'all' else ' OR '
        conditions = joiner.join('instr(lower(c.body),?)>0' for _ in terms)
        args = terms[:]
        scope = ' AND s.collection<>?'
        args.append(LEGACY_CARD_COLLECTION)
        if collection:
            scope += ' AND s.collection=?'
            args.append(collection)
        if path_prefix:
            scope += ' AND instr(s.path,?)=1'
            args.append(path_prefix)
        with self.store.connection() as db:
            rows = [dict(row) for row in db.execute(f'''SELECT c.body,c.line_start,c.line_end,
                s.id AS source_id,s.collection,s.path,s.fingerprint
                FROM chunks c JOIN sources s ON c.source_id=s.id
                WHERE s.active=1 AND ({conditions}){scope}''', args)]
        ranked = sorted(rows, key=lambda row: (
            -sum(term in row['body'].lower() for term in terms),
            row['collection'], row['path'], row['line_start'],
        ))
        hits, counts = [], {}
        for row in ranked:
            if len(hits) >= limit:
                break
            if counts.get(row['source_id'], 0) >= 2:
                continue
            counts[row['source_id']] = counts.get(row['source_id'], 0) + 1
            hits.append({
                **row,
                'document_ref': {
                    'kind': 'corpus_document',
                    'source_id': row['source_id'],
                    'fingerprint': row['fingerprint'],
                },
                'verification': 'indexed_unverified',
                'canon': False,
            })
        return {
            'query': query,
            'hits': hits,
            'total_matching_chunks': len(rows),
            'filters': {'collection': collection, 'path_prefix': path_prefix, 'match_mode': match_mode},
            'method': '关键词／子串检索；不是语义检索',
            'notice': '命中是可重建索引结果，不验证资料事实；未命中不能证明资料不存在。',
        }

    def read(self, source_id: int, expected_fingerprint: str, char_offset: int = 0, max_chars: int = 3000) -> dict:
        if not isinstance(source_id, int) or source_id < 1:
            raise ValueError('source_id必须为正整数')
        if not re.fullmatch(r'[0-9a-f]{64}', expected_fingerprint or ''):
            raise ValueError('expected_fingerprint必须为检索返回的SHA-256')
        if not isinstance(char_offset, int) or char_offset < 0 or not isinstance(max_chars, int) or not 1 <= max_chars <= 6000:
            raise ValueError('char_offset须非负；max_chars须为1–6000')
        with self.store.connection() as db:
            row = db.execute('SELECT collection,path,fingerprint,active FROM sources WHERE id=?', (source_id,)).fetchone()
            if not row or row['collection'] == LEGACY_CARD_COLLECTION:
                raise ValueError('corpus文档不存在')
            version = db.execute('SELECT body FROM source_versions WHERE source_id=? AND fingerprint=?',
                                 (source_id, expected_fingerprint)).fetchone()
        if not version:
            raise ValueError('corpus文档版本不存在')
        body = version['body']
        root = self._root(row['collection'])
        current_path = root / row['path']
        current_file_fingerprint = ''
        if (current_path.is_file() and not current_path.is_symlink()
                and current_path.resolve().is_relative_to(root)
                and current_path.stat().st_size <= MAX_FILE_BYTES):
            try:
                current_file_fingerprint = digest(current_path.read_text(encoding='utf-8-sig'))
            except (UnicodeError, OSError):
                current_file_fingerprint = ''
        index_current = bool(row['active']) and row['fingerprint'] == expected_fingerprint
        current = index_current and current_file_fingerprint == expected_fingerprint
        text = body[char_offset:char_offset + max_chars]
        next_offset = char_offset + len(text) if char_offset + len(text) < len(body) else None
        return {
            'source_id': source_id,
            'collection': row['collection'],
            'path': row['path'],
            'fingerprint': expected_fingerprint,
            'current': current,
            'source_state': 'current' if current else 'source_file_changed' if index_current else 'historical_index_version',
            'text': text,
            'char_offset': char_offset,
            'next_char_offset': next_offset,
            'total_characters': len(body),
            'verification': 'indexed_unverified',
            'canon': False,
        }
