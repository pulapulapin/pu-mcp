"""Long-form text workbench tools (module: longform). Neutral names; no domain defaults."""
import json
from typing import Literal
import novel_mcp
from novel_workbench import Workbench
from mcp.types import ToolAnnotations

# Public name -> legacy novel_* alias (compat module / owner preset).
LONGFORM_ALIASES = {
    'writing_get_state': 'novel_get_state',
    'writing_get_context': 'novel_get_context',
    'writing_resume': 'novel_start_session',
    'writing_validate': 'novel_validate',
    'writing_save_confirmed_decision': 'novel_save_confirmed_decision',
    'draft_list': 'novel_list_drafts',
    'draft_get': 'novel_read_draft',
    'draft_propose': 'novel_propose_draft',
    'draft_propose_edit': 'novel_propose_draft_edit',
    'draft_preview': 'novel_preview_draft',
    'draft_save': 'novel_save_draft',
    'draft_reject': 'novel_reject_draft',
    'draft_export': 'novel_export_draft',
    'library_list_books': 'novel_list_reference_books',
    'library_index_book': 'novel_index_reference_book',
    'library_get_structure': 'novel_get_book_structure',
    'library_read_excerpt': 'novel_read_book_excerpt',
    'library_search': 'novel_search_book',
    'library_register_book': 'novel_register_reference_book',
    'library_set_active': 'novel_set_reference_book_active',
    'library_inspect_file': 'novel_inspect_reference_file',
    'library_get_progress': 'novel_get_reading_progress',
    'library_record_progress': 'novel_record_reading_progress',
}


def _dump(payload):
    return json.dumps(payload, ensure_ascii=False)


def _fail(exc):
    return _dump({'ok': False, 'error': str(exc)})


def _task_context(payload, project):
    session = Workbench(project_id=project).resume(project)
    return {**payload, 'project_next_task': payload['next_task'],
            'next_task': {'label': session['stage'], 'instruction': session['task'], 'next_step': session['next_step'],
                          'task_id': session['task_id'], 'state': session['task_state'],
                          'direction_revision': session['direction_revision'],
                          'automatic_development_allowed': session['automatic_development_allowed']},
            'next_task_source': session['resume_mode'], 'session': session}


def _wb(action, project=''):
    try:
        return json.dumps({'ok': True, 'result': action(Workbench(project_id=project))}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False)


def _proposal_wb(action, proposal_id):
    """Locate an opaque proposal without guessing a project or silently crossing stores."""
    try:
        from novel_config import load_settings
        candidates = [Workbench()]
        for project, binding in sorted(load_settings().get('project_stores', {}).items()):
            if binding['mode'] == 'active':
                candidates.append(Workbench(project_id=project))
        matches = []
        seen = set()
        for workbench in candidates:
            key = str(workbench.store.path)
            if key in seen:
                continue
            seen.add(key)
            with workbench.store.connection() as db:
                if db.execute('SELECT 1 FROM proposals WHERE id=?', (proposal_id,)).fetchone():
                    matches.append(workbench)
        if len(matches) != 1:
            raise ValueError('候选不存在或跨存储重复；请重新发起预览')
        return json.dumps({'ok': True, 'result': action(matches[0])}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False)


class _AliasRegistration:
    """Register the same function under an additional MCP tool name."""

    def __init__(self, server, aliases):
        self.server = server
        self.aliases = aliases
        self._pending = {}

    def tool(self, **options):
        def decorate(function):
            public = function.__name__
            registered = self.server.tool(name=public, **options)(function)
            alias = self.aliases.get(public)
            if alias:
                self.server.tool(name=alias, **options)(function)
            return registered
        return decorate


def register_longform(server, aliases=False):
    """Register writing/draft/library tools. When aliases=True also expose novel_* names."""
    target = _AliasRegistration(server, LONGFORM_ALIASES) if aliases else server
    from story_planning_tools import register_story_planning
    register_story_planning(target)
    read = ToolAnnotations(read_only_hint=True)
    write = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)

    @target.tool()
    def writing_get_state(project: str) -> str:
        """读取项目状态、结构检查与同源会话任务；须显式project，无默认项目。只读。"""
        try:
            return _dump({'ok': True, **_task_context(novel_mcp.get_state(project), project)})
        except Exception as exc:
            return _fail(exc)

    @target.tool(annotations=read)
    def writing_get_context(project: str, prompt_id: str = '', max_chars: int = 140000,
                            source_ids: list[str] | None = None,
                            document_ranges: list[dict] | None = None,
                            include_source_map: bool = False,
                            source_facts: list[dict] | None = None) -> str:
        """只读恢复。source_ids选材料，document_ranges选正文范围。include_source_map返回标题来源索引。source_facts候选项含id/source_id/expected_fingerprint/kind(story_contract|character|timeline)/entity_id/field/value/quote，可选start_char/status_quote；仅核对引文，不认证含义或批准、不写入。"""
        try:
            from writing_context import recover
            payload = novel_mcp.get_context(project)
            recovery = recover(Workbench(project_id=project), project, prompt_id, max_chars, source_ids, document_ranges,
                               include_source_map, source_facts)
            if source_ids is not None:
                payload['context'] = {'omitted_by_request': True}
            task = recovery['task']
            if prompt_id == 'reader-reviewer':
                payload['context'] = {}
                payload['next_task'] = None
            result = {'ok': True, **payload, 'recovery': recovery,
                          'project_next_task': payload['next_task'],
                          'next_task': {'label': task['stage'], 'instruction': task['task'],
                                        'next_step': task['next_step'], 'task_id': task['task_id'],
                                        'state': task['task_state'], 'direction_revision': task['direction_revision'],
                                        'automatic_development_allowed': task['automatic_development_allowed']},
                          'next_task_source': task['resume_mode'],
                          'context_scope': 'context为旧JSON视图，recovery为显式来源恢复；二者不互相替代。'}
            if len(_dump(result)) > max_chars:
                if recovery['state'] == 'READY':
                    recovery['state'] = 'PARTIAL'
                recovery['delivery_complete'] = False
                recovery['issues'].append({'source': 'delivery', 'required': False,
                                           'reason': '完整响应超过预算；兼容JSON视图省略，须补读后才可声明完整恢复。'})
                result['context'] = {'content_omitted': True}
                recovery['allowed_scope'] = '仅讨论不依赖未交付材料的候选；不得声称完整恢复。'
            return _dump(result)
        except Exception as exc:
            return _fail(exc)

    @target.tool()
    def writing_resume(project: str, session_id: str = '') -> str:
        """按最高direction_revision或指定session_id恢复同源任务/阶段/下一步；须显式project。不恢复宿主完整聊天。"""
        try:
            return _dump({'ok': True, **novel_mcp.start_session(project), **Workbench(project_id=project).resume(project, session_id)})
        except Exception as exc:
            return _fail(exc)

    @target.tool(annotations=read)
    def writing_validate(project: str) -> str:
        """仅检查_storylab JSON结构；失败不代表外部Markdown/Canon缺失。不补写字段。只读。"""
        try:
            return _dump({'ok': True, **novel_mcp.validate(project),
                          'validation_scope': 'storylab_json_structure', 'external_documents_validated': False,
                          'next_task_scope': 'JSON结构补全建议，不替代当前会话方向；不授权编造或写入设定。'})
        except Exception as exc:
            return _fail(exc)

    @target.tool()
    def writing_save_confirmed_decision(project: str, field: str, value: str, owner_confirmed: bool = False, rationale: str = '') -> str:
        """兼容入口：禁用旧Canon写入；owner_confirmed不等于可信采纳证据。请将内容保留为独立草稿。"""
        return _dump({'ok': False, 'error': '禁用旧Canon写入：owner_confirmed参数不等于可信采纳证据。请将内容保留为独立草稿。'})

    @target.tool()
    def draft_list(project: str) -> str:
        """仅列本接口管理的版本化草稿；空列表不代表Markdown正文不存在。须显式project。"""
        return _wb(lambda w: w.store.list_drafts(w.project_id(project)), project)

    @target.tool(annotations=read)
    def draft_get(project: str, draft_id: str, revision: int = 0,
                  expected_fingerprint: str = '', review_items: list[dict] | None = None) -> str:
        """只读当前/历史草稿并返回正文SHA。审稿引用核对须revision>=1和expected_fingerprint，review_items每项id/quote及可选start_char(Unicode从0计)。不验证文学判断、不保存意见。"""
        def read_draft(w):
            from manuscript_review import check
            if review_items is not None and revision < 1:
                raise ValueError('核对审稿引用须指定固定revision>=1')
            return check(w.store.draft(w.project_id(project), draft_id, revision or None),
                         expected_fingerprint, review_items)
        return _wb(read_draft, project)

    @target.tool()
    def draft_propose(project: str, draft_id: str, title: str, body: str, baseline: int = 0) -> str:
        """保存候选修改并返回Diff；不修改草稿当前版本，不写Canonical文件。"""
        return _wb(lambda w: w.propose(project, draft_id, title, body, baseline), project)

    @target.tool()
    def draft_propose_edit(project: str, draft_id: str, selected_text: str, replacement: str, baseline: int) -> str:
        """仅替换唯一选中的原文并预览；未选中正文由程序保持不变。"""
        return _wb(lambda w: w.propose_edit(project, draft_id, selected_text, replacement, baseline), project)

    @target.tool()
    def draft_preview(proposal_id: str) -> str:
        """读取候选全文、原版本和差异，供展示给作者。"""
        return _proposal_wb(lambda w: w.store.preview(proposal_id), proposal_id)

    @target.tool()
    def draft_save(proposal_id: str, operation_key: str) -> str:
        """将候选保存为独立草稿新版本；应先展示差异。防冲突与重复，不确认Canon、不发布。"""
        return _proposal_wb(lambda w: w.store.commit_draft(proposal_id, operation_key), proposal_id)

    @target.tool()
    def draft_reject(proposal_id: str) -> str:
        """拒绝待处理候选，不改变当前草稿。"""
        return _proposal_wb(lambda w: w.store.reject(proposal_id), proposal_id)

    @target.tool()
    def draft_export(project: str, draft_id: str, revision: int = 0) -> str:
        """返回Markdown稿件，可保存为文件；不提交到发行平台。"""
        return _wb(lambda w: w.export(project, draft_id, revision or None), project)

    @target.tool(annotations=read)
    def library_list_books() -> str:
        """列出预配置参考TXT、作品work_id、book_id、原字节指纹及目录状态，不读取全文进上下文。"""
        return _wb(lambda w: w.books.list())

    @target.tool(annotations=write)
    def library_index_book(book_id: str, expected_fingerprint: str, baseline: int = 0, corrections: list[dict] | None = None) -> str:
        """只建立TXT章节位置索引，不保存全文或修改原著。传列表指纹及当前目录revision作为baseline。"""
        return _wb(lambda w: w.books.index(book_id, expected_fingerprint, baseline, corrections))

    @target.tool(annotations=read)
    def library_get_structure(book_id: str, offset: int = 0, limit: int = 50, revision: int = 0) -> str:
        """分页读取参考书目录和编码。chapter_id是版本:序号。"""
        return _wb(lambda w: w.books.structure(book_id, offset, limit, revision))

    @target.tool(annotations=read)
    def library_read_excerpt(book_id: str, chapter_id: str, expected_fingerprint: str, char_offset: int = 0, max_chars: int = 3000) -> str:
        """读取单章节有限原文，max_chars最多6000；用next_char_offset续读。原文仅为研究素材。"""
        return _wb(lambda w: w.books.read(book_id, chapter_id, expected_fingerprint, char_offset, max_chars))

    @target.tool(annotations=read)
    def library_search(book_id: str, query: str, expected_fingerprint: str, limit: int = 10, start_ordinal: int = 1, max_chapters: int = 50) -> str:
        """只在指定TXT中逐行字面查找；用next_start_ordinal继续。"""
        return _wb(lambda w: w.books.search(book_id, query, expected_fingerprint, limit, start_ordinal, max_chapters))

    from novel_library import register as register_book, set_active, progress, record_progress, inspect_file

    @target.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
    def library_register_book(book_id: str, title: str, relative_path: str, expected_fingerprint: str, baseline: int = 0) -> str:
        """注册books_root许可目录内已存在的TXT；只登记书目。"""
        return _wb(lambda w: register_book(w.books, book_id, title, relative_path, expected_fingerprint, baseline))

    @target.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
    def library_set_active(book_id: str, active: bool, baseline: int) -> str:
        """启用或停用参考书，不删除原著、章节索引或进度。"""
        return _wb(lambda w: set_active(w.books, book_id, active, baseline))

    @target.tool(annotations=read)
    def library_inspect_file(relative_path: str) -> str:
        """注册前检查books_root内指定TXT的存在、大小和原字节SHA256。"""
        return _wb(lambda w: inspect_file(w.books, relative_path))

    @target.tool(annotations=read)
    def library_get_progress(book_id: str, offset: int = 0, limit: int = 100) -> str:
        """读取当前目录的报告阅读状态。"""
        return _wb(lambda w: progress(w.books, book_id, offset, limit))

    @target.tool(annotations=write)
    def library_record_progress(book_id: str, chapter_ids: list[str], fingerprint: str, mode: Literal['complete', 'sampled', 'keyword_hit'], summary: str, baseline: int, operation_key: str) -> str:
        """仅记录实际执行/作者明确报告的阅读状态；非独立阅读证明。"""
        return _wb(lambda w: record_progress(w.books, book_id, chapter_ids, fingerprint, mode, summary, baseline, operation_key))

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def writing_preview_snapshot(project: str, session_id: str, snapshot: dict) -> str:
        """预览长文项目会话交接，不保存。"""
        return _wb(lambda w: w.conversations.preview(project, session_id, snapshot), project)

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True))
    def writing_save_snapshot(project: str, session_id: str, snapshot: dict, baseline: int, preview_fingerprint: str, operation_key: str) -> str:
        """保存已预览并获用户授权的会话交接版本。"""
        return _wb(lambda w: w.conversations.save(project, session_id, snapshot, baseline, preview_fingerprint, operation_key), project)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def writing_list_snapshots(project: str, session_id: str = '', offset: int = 0, limit: int = 20) -> str:
        """列出项目会话备份。"""
        return _wb(lambda w: w.conversations.list(project, session_id, offset, limit), project)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def writing_read_snapshot(project: str, session_id: str, revision: int, expected_fingerprint: str, char_offset: int = 0, max_chars: int = 3000) -> str:
        """读取固定版本交接JSON。"""
        return _wb(lambda w: w.conversations.read(project, session_id, revision, expected_fingerprint, char_offset, max_chars), project)
