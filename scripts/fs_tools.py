"""Optional local filesystem reader MCP tools (module: fs)."""
import json
from mcp.types import ToolAnnotations
from novel_config import load_settings
from workspace_fs import FsWorkspace, list_fs_workspaces


def register_fs(server):
    def fs_call(project, action):
        try:
            settings = load_settings()
            return json.dumps(
                {'ok': True, 'result': action(settings if project == '' else FsWorkspace(settings, project))},
                ensure_ascii=False)
        except Exception as exc:
            return json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def fs_workspace_status(project: str = '') -> str:
        """列出已启用fs只读的本地工作区；指定project时返回该区后缀/上限/deny。只读，不扫描文件内容。"""
        def run(settings_or_ws):
            if project:
                return settings_or_ws.status()
            return {'workspaces': list_fs_workspaces(settings_or_ws),
                    'policy': '本地工作区只读；未启用fs_read的项目不会出现。'}
        return fs_call(project, run)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def fs_list_files(project: str, path: str = '.', depth: int = 2, offset: int = 0, limit: int = 100) -> str:
        """在已配置fs工作区内按相对路径列表文本文件及SHA；depth限制递归。拒绝隐藏路径、穿越、符号链接与deny。"""
        return fs_call(project, lambda ws: ws.list_files(path, depth, offset, limit))

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def fs_read_file(project: str, path: str, expected_fingerprint: str, char_offset: int = 0, max_chars: int = 3000) -> str:
        """按相对路径与当前SHA读取文本片段，返回行号与续读偏移；最多6000字符。不执行文件内容。"""
        return fs_call(project, lambda ws: ws.read_file(path, expected_fingerprint, char_offset, max_chars))

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def fs_search(project: str, query: str, mode: str = 'and', limit: int = 20, path_prefix: str = '') -> str:
        """扫盘字面检索：mode=and/or/phrase；返回路径、行号、片段与指纹。未命中不证明资料不存在。"""
        return fs_call(project, lambda ws: ws.search(query, mode, limit, path_prefix))
