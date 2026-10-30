"""Read-only project-store placement and migration planning."""
import json
import os
from pathlib import Path
import uuid

from novel_evidence import encode
from novel_store import Store, digest, identifier


PROJECT_TABLES = (
    'checkpoints', 'drafts', 'draft_versions', 'proposals', 'operations',
    'handoff_versions', 'research_annotation_versions', 'research_project_links',
    'session_backup_versions', 'voice_record_versions',
)


class ProjectStorage:
    def __init__(self, workspace):
        self.w = workspace

    def placement(self, project):
        identifier(project)
        configured = Path(self.w.project(project)).resolve()
        root = configured.parent if configured.name == '_storylab' else configured
        target_dir = root / '.puknowledge'
        return configured, root, target_dir, target_dir / 'workspace.sqlite3'

    def get(self, project):
        configured, root, target_dir, target = self.placement(project)
        return {
            'project': project,
            'configured_project_path': str(configured),
            'project_root': str(root),
            'storylab_path': str(configured) if configured.name == '_storylab' else None,
            'active_store': str(self.w.store.path),
            'active_mode': 'shared',
            'proposed_store_directory': str(target_dir),
            'proposed_store': str(target),
            'proposed_store_exists': target.exists(),
            'routing_changed': False,
            'notice': 'Read-only status. Project routing still uses the shared store.',
        }

    @staticmethod
    def _count(db, table, project):
        return db.execute(f'SELECT COUNT(*) FROM {table} WHERE project=?', (project,)).fetchone()[0]

    @staticmethod
    def _columns(db, table):
        return [row[1] for row in db.execute(f'PRAGMA table_info({table})')]

    def _rows(self, db, table, where='', args=()):
        columns = self._columns(db, table)
        query = f'SELECT {",".join(columns)} FROM {table}'
        if where:
            query += ' WHERE ' + where
        rows = [dict(row) for row in db.execute(query, args)]
        rows.sort(key=encode)
        return rows

    @staticmethod
    def _manifest(rows):
        return {'count': len(rows), 'fingerprint': digest(encode(rows))}

    def _closure(self, db, project):
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        project_rows = {
            table: self._rows(db, table, 'project=?', (project,))
            for table in PROJECT_TABLES if table in tables
        }
        dataset_ids = []
        rows = db.execute("SELECT object_id,body FROM knowledge_versions WHERE kind='dataset' "
                          "ORDER BY object_id,revision DESC").fetchall()
        seen = set()
        for row in rows:
            if row['object_id'] in seen:
                continue
            seen.add(row['object_id'])
            body = json.loads(row['body'])
            if body.get('scope') == 'project' and body.get('owner_project') == project:
                dataset_ids.append(row['object_id'])
        dataset_ids.sort()
        knowledge_rows = []
        if dataset_ids:
            marks = ','.join('?' for _ in dataset_ids)
            knowledge_rows = self._rows(db, 'knowledge_versions',
                                        f'dataset_id IN ({marks})', dataset_ids)

        private_source_ids = []
        if 'research_sources' in tables:
            private_source_ids = [row[0] for row in db.execute(
                'SELECT id FROM research_sources WHERE scope=? AND owner_project=? ORDER BY id',
                ('project', project))]
        referenced_source_ids = set()
        for row in project_rows.get('research_project_links', []):
            referenced_source_ids.add(row['source_id'])
        for row in project_rows.get('research_annotation_versions', []):
            referenced_source_ids.add(row['source_id'])
        source_ids = sorted(set(private_source_ids) | referenced_source_ids)
        research_sources, research_versions = [], []
        if source_ids:
            marks = ','.join('?' for _ in source_ids)
            research_sources = self._rows(db, 'research_sources', f'id IN ({marks})', source_ids)
            research_versions = self._rows(db, 'research_source_versions',
                                           f'source_id IN ({marks})', source_ids)
        dependency_source_ids = sorted(set(source_ids) - set(private_source_ids))
        return {
            'project_rows': project_rows,
            'dataset_ids': dataset_ids,
            'knowledge_rows': knowledge_rows,
            'private_source_ids': private_source_ids,
            'dependency_source_ids': dependency_source_ids,
            'research_sources': research_sources,
            'research_versions': research_versions,
        }

    def _closure_manifest(self, closure):
        tables = {name: self._manifest(rows)
                  for name, rows in closure['project_rows'].items()}
        tables['knowledge_versions'] = self._manifest(closure['knowledge_rows'])
        tables['research_sources'] = self._manifest(closure['research_sources'])
        tables['research_source_versions'] = self._manifest(closure['research_versions'])
        return {
            'tables': tables,
            'dataset_ids': closure['dataset_ids'],
            'private_source_ids': closure['private_source_ids'],
            'dependency_source_ids': closure['dependency_source_ids'],
            'fingerprint': digest(encode(tables)),
        }

    def preview(self, project):
        status = self.get(project)
        with self.w.store.connection() as db:
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            schema = db.execute('PRAGMA user_version').fetchone()[0]
            closure = self._closure(db, project)
            manifest = self._closure_manifest(closure)
            counts = {table: item['count'] for table, item in manifest['tables'].items()
                      if table in PROJECT_TABLES}
            global_dependencies = {
                'legacy_sources': 'remain_global_by_fixed_source_id_and_fingerprint',
                'reference_library': 'remain_global',
                'global_datasets': 'remain_global_by_fixed_dataset_revision',
                'research_source_dependency_replicas': manifest['dependency_source_ids'],
            }
        payload = {
            **status,
            'source_integrity': integrity,
            'source_schema_version': schema,
            'project_table_counts': counts,
            'project_dataset_ids': manifest['dataset_ids'],
            'project_knowledge_versions': manifest['tables']['knowledge_versions']['count'],
            'private_research_source_ids': manifest['private_source_ids'],
            'private_research_source_versions': sum(
                1 for row in closure['research_versions']
                if row['source_id'] in set(manifest['private_source_ids'])),
            'dependency_research_source_ids': manifest['dependency_source_ids'],
            'migration_manifest': manifest['tables'],
            'migration_manifest_fingerprint': manifest['fingerprint'],
            'global_dependencies': global_dependencies,
            'target_relative_path': '.puknowledge/workspace.sqlite3',
            'migration_mode': 'shadow_copy_then_read_only_cutover',
            'writes_performed': False,
            'routing_changed': False,
        }
        issues = []
        if integrity != 'ok':
            issues.append({'code': 'source_integrity_failed', 'reason': integrity})
        if status['proposed_store_exists']:
            issues.append({'code': 'target_exists',
                           'reason': 'Target database already exists and must be inspected before migration.'})
        payload['state'] = 'BLOCKED' if issues else 'PREVIEW_READY'
        payload['issues'] = issues
        payload['preview_fingerprint'] = digest(encode(payload))
        payload['next_action'] = ('Resolve blocking issues.' if issues else
                                  'Review this exact project closure before any shadow copy is created.')
        return payload

    @staticmethod
    def _insert_rows(db, table, rows):
        if not rows:
            return
        columns = list(rows[0])
        marks = ','.join('?' for _ in columns)
        db.executemany(
            f'INSERT INTO {table} ({",".join(columns)}) VALUES ({marks})',
            [[row[column] for column in columns] for row in rows],
        )

    def shadow_copy(self, project, preview_fingerprint):
        if not isinstance(preview_fingerprint, str) or len(preview_fingerprint) != 64:
            raise ValueError('preview_fingerprint must be the exact 64-character preview fingerprint')
        preview = self.preview(project)
        if preview['state'] != 'PREVIEW_READY':
            raise ValueError('project storage preview is blocked')
        if preview['preview_fingerprint'] != preview_fingerprint:
            raise ValueError('project storage preview changed; preview again before shadow copy')
        _, _, target_dir, target = self.placement(project)
        if target.exists():
            raise ValueError('target project database already exists')
        with self.w.store.connection() as source:
            closure = self._closure(source, project)
            source_manifest = self._closure_manifest(closure)
        target_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = target_dir / ('.shadow-' + uuid.uuid4().hex)
        temp_store = None
        try:
            temp_store = Store(temp_dir)
            with temp_store.connection(write=True) as db:
                self._insert_rows(db, 'research_sources', closure['research_sources'])
                self._insert_rows(db, 'research_source_versions', closure['research_versions'])
                for table, rows in closure['project_rows'].items():
                    self._insert_rows(db, table, rows)
                self._insert_rows(db, 'knowledge_versions', closure['knowledge_rows'])
                integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
                foreign_keys = [dict(row) for row in db.execute('PRAGMA foreign_key_check')]
                if integrity != 'ok' or foreign_keys:
                    raise ValueError('shadow database integrity validation failed')
            os.replace(temp_store.path, target)
            temp_dir.rmdir()
        except BaseException:
            if temp_store and temp_store.path.exists():
                temp_store.path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()
            raise
        result = self.verify(project)
        if not result['matches_source']:
            target.unlink()
            try:
                target_dir.rmdir()
            except OSError:
                pass
            raise ValueError('shadow database differs from source project closure')
        return {
            **result,
            'copied': True,
            'routing_changed': False,
            'active_store': str(self.w.store.path),
            'notice': 'Shadow copy created and verified. Runtime still reads the shared store.',
            'source_manifest_fingerprint': source_manifest['fingerprint'],
        }

    def verify(self, project):
        _, _, _, target = self.placement(project)
        if not target.exists():
            raise ValueError('target project database does not exist')
        with self.w.store.connection() as source:
            source_closure = self._closure(source, project)
            source_manifest = self._closure_manifest(source_closure)
        target_store = Store(target.parent)
        with target_store.connection() as db:
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            foreign_keys = [dict(row) for row in db.execute('PRAGMA foreign_key_check')]
            target_closure = self._closure(db, project)
            target_manifest = self._closure_manifest(target_closure)
        return {
            'project': project,
            'target_store': str(target),
            'target_integrity': integrity,
            'foreign_key_issues': foreign_keys,
            'source_manifest': source_manifest,
            'target_manifest': target_manifest,
            'matches_source': (integrity == 'ok' and not foreign_keys and
                               source_manifest == target_manifest),
            'routing_changed': False,
        }
