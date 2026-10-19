# Public MCP API

`workspace_guide` 是首选入口。服务返回统一的 `{ok,result}` 或 `{ok:false,error}` JSON。

| 模块 | 工具组 |
|---|---|
| core | `workspace_*`、`task_*`、`source_*`、`evidence_*`、`capture_*`、`dataset_*`、`schema_*`、`record_*`、`relation_*`、`import_*` |
| fs | `fs_workspace_status`、`fs_list_files`、`fs_read_file`、`fs_search` |
| longform | `writing_*`、`draft_*`、`library_*` |

项目参数必须显式提供。任务、来源、证据、观点和工具结果分别存储。写入前先预览；提交必须绑定预览指纹、当前基线和幂等键。查询不提供任意 SQL，导入不执行公式或输入文件中的代码。
