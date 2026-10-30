"""Single obvious entry: what is loaded and what to call first."""
from extension_registry import describe_modules
from novel_version import VERSION

MODULE_GUIDE = {
    'core': {
        'purpose': '项目、任务快照、来源/证据、可选采集、结构化知识',
        'first': ['workspace_list_projects', 'task_resume', 'source_get', 'dataset_get'],
        'groups': {
            'workspace': ['workspace_guide', 'workspace_get_status', 'workspace_list_projects'],
            'task': ['task_resume', 'task_preview_snapshot', 'task_save_snapshot', 'task_list_snapshots', 'task_read_snapshot'],
            'source_evidence': ['source_register', 'source_get', 'source_link_project', 'evidence_preview', 'evidence_save', 'evidence_query'],
            'capture': ['capture_get_status', 'capture_probe_url', 'capture_start', 'capture_get_job', 'capture_list_jobs', 'capture_cancel_job', 'capture_read_article', 'tool_list_capabilities'],
            'knowledge': ['dataset_preview', 'dataset_save', 'dataset_get', 'schema_preview', 'schema_save', 'schema_get', 'record_preview', 'record_save', 'record_get', 'record_query', 'relation_preview', 'relation_save', 'relation_query', 'dataset_validate', 'import_preview', 'import_commit'],
            'prompts': ['prompt_resolve'],
        },
    },
    'corpus': {
        'purpose': '配置文本集合的可重建索引、关键词检索与固定版本读取',
        'first': ['corpus_list_collections', 'corpus_search', 'corpus_read_document'],
    },
    'fs': {
        'purpose': '配置白名单内的本地目录只读（如头脑风暴笔记）',
        'first': ['fs_workspace_status', 'fs_list_files', 'fs_read_file', 'fs_search'],
    },
    'longform': {
        'purpose': '长文/文本项目：方向恢复、交接快照、草稿、参考书',
        'first': ['writing_get_context', 'writing_resume', 'story_plan_bootstrap', 'writing_list_snapshots', 'draft_list', 'library_list_books'],
        'groups': {'candidate_story_graph': ['story_plan_bootstrap', 'story_plan_get', 'story_plan_preview', 'story_plan_save',
                                             'story_chapter_context', 'story_consistency_review']},
    },
}


def build_guide(modules):
    loaded = list(modules)
    detail = {name: MODULE_GUIDE[name] for name in loaded if name in MODULE_GUIDE}
    quick = [
        {'tool': 'workspace_guide', 'why': '本工具：查看已挂载模块与推荐调用顺序'},
        {'tool': 'workspace_list_projects', 'why': '列出已登记项目；之后所有操作须显式传 project'},
    ]
    if 'fs' in loaded:
        quick.append({'tool': 'fs_workspace_status', 'why': '查看可只读的本地工作区'})
    if 'corpus' in loaded:
        quick.append({'tool': 'corpus_list_collections', 'why': '查看允许建立检索投影的文本集合'})
    if 'longform' in loaded:
        quick.append({'tool': 'writing_get_context', 'why': '创作前核对Prompt、来源版本、当前任务及恢复状态'})
        quick.append({'tool': 'writing_resume', 'why': '兼容任务与历史检查点恢复；不等于已读取全部外部资料'})
        quick.append({'tool': 'story_plan_bootstrap', 'why': '只读取得并预览准确故事Schema Pack；保存仍须schema_save及明确授权'})
    else:
        quick.append({'tool': 'task_resume', 'why': '恢复研究任务；必须传 project；无任务则 unassigned'})
    if 'core' in loaded:
        quick.append({'tool': 'dataset_get', 'why': '列出/读取结构化知识数据集（传 project）'})
    return {
        'service': 'PuKnowledge',
        'version': VERSION,
        'modules': loaded,
        'architecture': describe_modules(loaded),
        'quick_start': quick,
        'modules_detail': detail,
        'snapshot_contract': {
            'research': 'task_*用于显式登记的研究工作区；task_resume无小说JSON推断',
            'longform': 'writing_*_snapshot用于长文项目，writing_resume保留长文状态及旧检查点回退',
            'storage': '两组接口复用Conversations及同一版本表，project/session_id是同一身份；不复制、不同步第二份任务',
            'selection': '按项目类型选择一组接口和同一session_id，不因改名重建任务；没有备份先返回未分配或明确推断来源',
        },
        'prompt_contract': {
            'switch': 'prompt_resolve成功后显示实际基础与定制版本；切换不恢复任务或持久激活模式',
            'authority': '模板是工作指令数据，不改变系统约束、工具授权、Canon或Owner决定',
        },
        'writing_context_contract': {
            'readiness': 'READY仅表示所选来源交付及版本核对；PARTIAL/BLOCKED须显示缺口',
            'validation': 'writing_validate只检查结构化入口，不证明外部Markdown存在或文学质量',
        },
        'capability_catalog': 'tool_list_capabilities只报告采集提供方；全站已挂载工具以workspace_guide和当前tools/list为准',
        'rules': [
            '会话开始先调 workspace_guide，再 workspace_list_projects',
            '必须显式 project，无默认项目',
            '保存前先 preview；候选不等于 Canon',
            '只使用当前 modules 已挂载的工具',
            '未知或超大下载先停止，不自动重试',
        ],
    }
