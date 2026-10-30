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
