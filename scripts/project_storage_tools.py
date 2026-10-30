"""Read-only MCP transport for project database placement planning."""
import json
from mcp.types import ToolAnnotations
from knowledge_api import workspace
from project_storage import ProjectStorage


def register_project_storage(server):
    def call(method, **args):
        try:
            result = getattr(ProjectStorage(workspace()), method)(**args)
            return json.dumps({'ok': True, 'result': result}, ensure_ascii=False)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            return json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def project_storage_get(project: str) -> str:
        """Show the active shared database and the project-local .puknowledge target. Read-only; does not create directories, move data or change routing."""
        return call('get', project=project)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def project_storage_preview(project: str) -> str:
        """Calculate the project-owned migration closure, global dependencies and blockers. Read-only; no database or project files are created."""
        return call('preview', project=project)

    @server.tool(annotations=ToolAnnotations(destructive_hint=False))
    def project_storage_shadow_copy(project: str, preview_fingerprint: str) -> str:
        """Create and verify an isolated project database from the exact approved preview. The active shared-store routing is not changed."""
        return call('shadow_copy', project=project, preview_fingerprint=preview_fingerprint)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def project_storage_verify(project: str) -> str:
        """Compare an existing project shadow database with the current project-owned source closure. Read-only."""
        return call('verify', project=project)
