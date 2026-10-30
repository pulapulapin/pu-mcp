"""Read-only project-store placement and migration planning."""
import json
from pathlib import Path

from novel_evidence import encode
from novel_store import digest, identifier


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

    def preview(self, project):
        status = self.get(project)
        with self.w.store.connection() as db:
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            schema = db.execute('PRAGMA user_version').fetchone()[0]
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts = {table: self._count(db, table, project)
                      for table in PROJECT_TABLES if table in tables}
            datasets = []
            rows = db.execute("SELECT object_id,body FROM knowledge_versions WHERE kind='dataset' "
                              "ORDER BY object_id,revision DESC").fetchall()
            seen = set()
            for row in rows:
                if row['object_id'] in seen:
                    continue
                seen.add(row['object_id'])
                body = json.loads(row['body'])
                if body.get('scope') == 'project' and body.get('owner_project') == project:
                    datasets.append(row['object_id'])
            knowledge_versions = 0
            if datasets:
                marks = ','.join('?' for _ in datasets)
                knowledge_versions = db.execute(
                    f'SELECT COUNT(*) FROM knowledge_versions WHERE dataset_id IN ({marks})', datasets
                ).fetchone()[0]
            private_sources = []
            if 'research_sources' in tables:
                private_sources = [row[0] for row in db.execute(
                    'SELECT id FROM research_sources WHERE scope=? AND owner_project=? ORDER BY id',
                    ('project', project),
                )]
            source_versions = 0
            if private_sources:
                marks = ','.join('?' for _ in private_sources)
                source_versions = db.execute(
                    f'SELECT COUNT(*) FROM research_source_versions WHERE source_id IN ({marks})',
                    private_sources,
                ).fetchone()[0]
            global_dependencies = {
                'legacy_sources': 'remain_global_by_fixed_source_id_and_fingerprint',
                'reference_library': 'remain_global',
                'global_datasets': 'remain_global_by_fixed_dataset_revision',
            }
        payload = {
            **status,
            'source_integrity': integrity,
            'source_schema_version': schema,
            'project_table_counts': counts,
            'project_dataset_ids': datasets,
            'project_knowledge_versions': knowledge_versions,
            'private_research_source_ids': private_sources,
            'private_research_source_versions': source_versions,
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
