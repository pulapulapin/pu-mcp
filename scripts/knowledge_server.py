"""Stable public protocol names over the shared core; no domain defaults."""

PUBLIC_NAMES = {
    'research_workspace_status': 'workspace_get_status', 'research_list_projects': 'workspace_list_projects',
    'research_start_session': 'task_resume', 'research_preview_session_backup': 'task_preview_snapshot',
    'research_save_session_backup': 'task_save_snapshot', 'research_list_session_backups': 'task_list_snapshots',
    'research_read_session_backup': 'task_read_snapshot', 'research_list_capabilities': 'tool_list_capabilities',
    'research_register_source': 'source_register', 'research_get_source': 'source_get', 'research_link_project': 'source_link_project',
    'research_preview_annotation': 'evidence_preview', 'research_save_annotation': 'evidence_save', 'research_get_annotations': 'evidence_query',
    'research_capture_status': 'capture_get_status', 'research_probe_url': 'capture_probe_url', 'research_start_capture': 'capture_start',
    'research_capture_job': 'capture_get_job', 'research_list_capture_jobs': 'capture_list_jobs',
    'research_cancel_capture': 'capture_cancel_job', 'research_read_captured_article': 'capture_read_article',
}


class PublicRegistration:
    def __init__(self, server):
        self.server = server

    def tool(self, **options):
        def decorate(function):
            return self.server.tool(name=PUBLIC_NAMES[function.__name__], **options)(function)
        return decorate


def create_server(modules=None, preset=None, aliases=False, research_aliases=False):
    from module_server import create_server as build
    if modules is None and preset is None:
        preset = 'workspace'
    return build(modules=modules, preset=preset, aliases=aliases, research_aliases=research_aliases)
