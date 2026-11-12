"""MCP registration for the optional neutral corpus extension."""
import json

from corpus import Corpus
from mcp.types import ToolAnnotations


def register_corpus(server):
    def call(action):
        try:
            return json.dumps({'ok': True, 'result': action(Corpus())}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False)

    read = ToolAnnotations(read_only_hint=True)
    write = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)

    @server.tool(annotations=read)
    def corpus_list_collections() -> str:
        """列出配置允许的文本集合；不扫描未登记目录。"""
        return call(lambda corpus: corpus.list())

    @server.tool(annotations=read)
    def corpus_preview_index(collection: str) -> str:
        """预览集合文件相对当前索引的新增、更新、停用与跳过项；不保存。"""
        return call(lambda corpus: corpus.preview_index(collection))

    @server.tool(annotations=write)
    def corpus_commit_index(collection: str, preview_fingerprint: str) -> str:
        """绑定最新预览指纹重建SQLite检索投影；不修改原文件或项目事实。"""
        return call(lambda corpus: corpus.commit_index(collection, preview_fingerprint))

    @server.tool(annotations=read)
    def corpus_search(query: str, limit: int = 6, collection: str = '', path_prefix: str = '', match_mode: str = 'any') -> str:
        """对已索引集合执行受限关键词检索；不做语义推断或领域版本判断。"""
        return call(lambda corpus: corpus.search(query, limit, collection, path_prefix, match_mode))

    @server.tool(annotations=read)
    def corpus_read_document(source_id: int, expected_fingerprint: str, char_offset: int = 0, max_chars: int = 3000) -> str:
        """按检索返回的整数ID和准确指纹分页读取固定文档版本。"""
        return call(lambda corpus: corpus.read(source_id, expected_fingerprint, char_offset, max_chars))
