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
