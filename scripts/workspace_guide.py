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
            'project_storage': ['project_storage_get', 'project_storage_preview',
                                'project_storage_shadow_copy', 'project_storage_verify',
                                'project_storage_sync_preview', 'project_storage_sync'],
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
        'purpose': '长文/文本项目：方向恢复、交接快照、草稿、参考书、候选故事图',
        'first': ['writing_get_context', 'writing_resume', 'story_plan_bootstrap', 'story_chapter_context',
                  'writing_list_snapshots', 'draft_list', 'library_list_books'],
        'groups': {'candidate_story_graph': ['story_plan_bootstrap', 'story_plan_get', 'story_plan_preview',
                                             'story_plan_save', 'story_chapter_context',
                                             'story_consistency_review']},
    },
    'writing_legacy': {
        'purpose': '过渡模块：collections资料索引/研究卡/旧检查点；非日常默认，后续单独收口',
        'first': ['novel_index_research', 'novel_search_research', 'novel_preview_research_card'],
    },
    'game': {
        'purpose': '游戏仓只读与联合创作 handoff',
        'first': ['game_repository_status', 'project_get_status'],
    },
    'voice': {
        'purpose': '声音试验记录（不运行 TTS）',
        'first': ['voice_list_records'],
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
        quick.append({'tool': 'writing_get_context', 'why': '创作前统一核对Prompt/来源版本/当前任务及恢复状态；须显式project，无默认项目'})
        quick.append({'tool': 'writing_resume', 'why': '兼容任务/历史检查点恢复；返回不等于已加载外部Canon和正文'})
        quick.append({'tool': 'story_plan_bootstrap', 'why': '只读取得并预览准确故事Schema Pack；保存仍须schema_save及明确授权'})
        quick.append({'tool': 'story_chapter_context', 'why': '从固定版本候选故事图恢复章节相关节点；不替代正文、Canon或完整创作上下文'})
    else:
        quick.append({'tool': 'task_resume', 'why': '恢复研究任务；必须传 project；无任务则 unassigned'})
    if 'core' in loaded:
        quick.append({'tool': 'dataset_get', 'why': '列出/读取结构化知识数据集（传 project）'})
        quick.append({'tool': 'project_storage_get', 'why': '只读核对项目数据库当前路由与建议的项目内存储位置'})
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
            'discover': 'dataset_get列可访问数据集；record_query按prompt_template/prompt_customization和lifecycle=active查询，读完分页；区分项目已采用与仅全局可试用模式',
            'switch': 'prompt_resolve成功后显示实际基础/定制revision再使用；仅切换模式不调用task/writing恢复、采集或写入工具；失败不凭记忆假装加载',
            'temporary': '本轮要求留在Chat或turn_instruction；Chat内已选模式可延续至切换/退出；未选择模式时自然对话，新Chat或上下文缺失时重新读取；不保存持久激活模式',
            'edit': '现有record_preview/save管理模板；预览差异并获得Owner授权后保存，预览指纹不是授权凭据',
            'context': '按模板context_policy及当前任务按需取材；解析不自动读取正文/Canon/作者意图，也不改变批准状态',
            'authority': '模板是工作指令数据，不改变系统约束、工具授权、已批准Canon或Owner决定；自然语言冲突不保证自动识别',
        },
        'writing_context_contract': {
            'entry': 'writing_get_context(project,prompt_id可选)只读调用正式Prompt解析并恢复writing_contexts显式绑定来源；不激活持久模式。仅切换模式仍用prompt_resolve，不自动恢复任务。',
            'readiness': 'READY=所选来源完整交付且版本匹配；PARTIAL=未配置、可选材料缺失或响应省略；BLOCKED=关键来源/任务不可用。宿主截断必须补读并降级，不能以READY证明模型已理解或行为通过。',
            'authority': '保留Markdown段落原状态；当前快照仅决定工作方向，不批准Canon。reader-reviewer显式调用仅取正文，不附作者任务意图；同一Chat已有上下文无法消除。',
            'validation': 'writing_validate只检查_storylab JSON结构；false不证明外部资料不存在。draft_list仅列接口版本化草稿，空列表不证明Markdown正文缺失。',
            'cached_clients': '若宿主未暴露prompt_resolve，已有writing_get_context可返回后端正式解析结果；不能假称客户端已经暴露新增工具。',
        },
        'capability_catalog': 'tool_list_capabilities只报告采集提供方；全站已挂载工具以workspace_guide和当前tools/list为准',
        'rules': [
            '会话开始先调 workspace_guide，再 workspace_list_projects',
            '必须显式 project，无默认项目',
            '保存前先 preview；候选不等于 Canon',
            '只使用当前 modules 已挂载的工具；不要假设 novel_* 别名存在',
            '未知或超大下载先停止，不自动重试',
        ],
    }
