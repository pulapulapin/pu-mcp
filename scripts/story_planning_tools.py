"""Optional longform transport for candidate graphs; core remains unchanged."""
import json
from mcp.types import ToolAnnotations
from knowledge_api import workspace
from story_planning import StoryPlanning, ChangeSet


def register_story_planning(server):
    def call(method, **args):
        try:
            result = getattr(StoryPlanning(workspace()), method)(**args)
            return json.dumps({'ok': True, 'result': result}, ensure_ascii=False)
        except (ValueError, TypeError, KeyError) as exc:
            return json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def story_plan_bootstrap(project: str, dataset_id: str) -> str:
        """Return and preview the exact supported story_node Schema Pack for an empty project-private model dataset. Never saves or overwrites schema; use returned arguments with schema_save only after review and authorization."""
        return call('bootstrap', project=project, dataset_id=dataset_id)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def story_plan_get(project: str, dataset_id: str, dataset_revision: int = 0,
                       offset: int = 0, limit: int = 50) -> str:
        """Read a project-private candidate graph snapshot. Reuse returned dataset_revision for pagination; no Canon or complete-context claim."""
        return call('get', project=project, dataset_id=dataset_id,
                    dataset_revision=dataset_revision, offset=offset, limit=limit)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def story_plan_preview(project: str, dataset_id: str, baseline: int, change_set: ChangeSet) -> str:
        """Preview candidate node/edge edits and explicit dependency paths; no persistent writes. Dataset/schema must already exist; not literary validation."""
        return call('preview', project=project, dataset_id=dataset_id, baseline=baseline,
                    change_set=change_set.model_dump(mode='json'))

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True))
    def story_plan_save(project: str, dataset_id: str, baseline: int, change_set: ChangeSet,
                        preview_fingerprint: str, operation_key: str) -> str:
        """Save an authorized candidate graph change set atomically using preview/baseline/idempotency. Does not modify manuscripts, task direction or Canon."""
        return call('save', project=project, dataset_id=dataset_id, baseline=baseline,
                    change_set=change_set.model_dump(mode='json'),
                    preview_fingerprint=preview_fingerprint, operation_key=operation_key)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def story_chapter_context(project: str, dataset_id: str, chapter_id: str,
                              dataset_revision: int = 0, mode: str = 'author',
                              max_nodes: int = 200) -> str:
        """Read a bounded chapter graph context at one dataset revision. Author mode returns registered candidate planning only; reader mode withholds candidate/future plans. No external manuscript or Canon claim."""
        return call('chapter_context', project=project, dataset_id=dataset_id,
                    chapter_id=chapter_id, dataset_revision=dataset_revision,
                    mode=mode, max_nodes=max_nodes)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def story_consistency_review(project: str, dataset_id: str,
                                 dataset_revision: int = 0,
                                 scope_ids: list[str] | None = None,
                                 checks: list[str] | None = None,
                                 max_findings: int = 100) -> str:
        """Check only explicit graph evidence: stale endpoints, comparable exclusive-location overlaps and state prerequisites. Missing assertions return insufficient_evidence; literary quality and Canon are never verified."""
        return call('consistency_review', project=project, dataset_id=dataset_id,
                    dataset_revision=dataset_revision, scope_ids=scope_ids,
                    checks=checks, max_findings=max_findings)
