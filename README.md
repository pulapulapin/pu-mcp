# PuKnowledge

**面向长期研究与创作项目的、可追溯 AI 工作上下文与证据管理 MCP。**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

PuKnowledge 把聊天模型作为推理入口，把本地 MCP 作为可核对的工作台。任务方向、来源版本、证据引用、结构化知识和长文快照保存在用户指定的本地目录，换聊天窗口或 MCP 客户端后仍可按明确项目恢复。

## 能力

- `core`：项目清单、任务恢复、快照、来源、证据、受控采集接口和结构化知识。
- `fs`：只读访问配置白名单中的工作区文件。
- `longform`：长文项目状态、草稿版本、参考书索引和写作快照。

服务不默认选择项目，不自动导入聊天历史，不遍历未授权目录，也不执行资料中的指令。写入流程使用预览、版本基线、内容指纹和幂等键。

架构采用“**通用基础 + 按需扩展 + 领域数据包**”：`core` 是固定基础，`fs` 和 `longform` 按需求加载。小说共享通用长文能力；D&D 等具体规则体系应作为有版本、有证据的领域数据，而不是基础 API 的硬编码。详见[基础与扩展架构](docs/EXTENSION-ARCHITECTURE.md)。

## 安装

需要 Python 3.11 或更高版本。

```bash
git clone https://github.com/pulapulapin/pu-mcp.git
cd pu-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp config/workspace.example.json config/workspace.local.json
.venv/bin/pu-knowledge-workbench \
  --config config/workspace.local.json \
  --check-config
```

`config/workspace.local.json` 使用本机路径，不应提交。相对路径以配置文件所在目录为基准。

## MCP 配置

```json
{
  "mcpServers": {
    "pu-knowledge-workbench": {
      "command": "/absolute/path/to/pu-mcp/.venv/bin/pu-knowledge-workbench",
      "args": [
        "--config",
        "/absolute/path/to/pu-mcp/config/workspace.local.json",
        "--modules",
        "core,fs,longform"
      ]
    }
  }
}
```

支持本地 stdio 的宿主可以直接启动以上命令。云端聊天宿主不能直接访问用户电脑上的 stdio 进程；这类宿主需要用户自行部署受保护的 HTTPS MCP 入口。GitHub 仓库授权只提供代码访问，不会自动运行 MCP 或开放本地数据。

桌面插件的绑定步骤见 [DESKTOP-PLUGIN](docs/DESKTOP-PLUGIN.md)。

## 最小使用顺序

1. 调用 `workspace_guide` 查看当前挂载模块。
2. 调用 `workspace_list_projects`，由用户明确选择项目。
3. 研究项目使用 `task_resume`；长文项目使用 `writing_resume`。
4. 保存前调用对应 `*_preview_*` 工具，并使用返回的基线与指纹提交。

接口清单见 [API](docs/API.md)，存储设计见 [ARCHITECTURE](docs/ARCHITECTURE.md)，结构化知识模型见 [STRUCTURED-KNOWLEDGE](docs/STRUCTURED-KNOWLEDGE.md)。

## 本地数据

仓库不包含数据库、业务资料、项目备份、凭据或作者本机配置。默认忽略 `.local/`、`workspace/`、数据库文件、`.env` 和本地 MCP 配置。已有数据是否复用由配置中的 `data_dir` 决定；安装代码本身不迁移或复制数据库。

## 开发验证

```bash
.venv/bin/python -B -m unittest discover -s tests
```

测试只使用临时目录和合成数据，不需要真实项目或外部下载。

## 发布状态

当前版本为 `0.3.3` 开发预览。程序代码采用 [Apache License 2.0](LICENSE)；该许可不自动覆盖用户数据库、小说正文、研究资料、项目文件或媒体内容。可选 Magpie/PuCatch 以各自仓库的许可为准。安全边界面向单用户、受信任的本地工作区，不是多租户权限系统。

安全问题请按 [SECURITY.md](SECURITY.md) 私下报告；参与开发见 [CONTRIBUTING.md](CONTRIBUTING.md)。

### Candidate story planning (development)

With `longform` enabled, `story_plan_get`, `story_plan_preview` and
`story_plan_save` manage a bounded candidate graph using existing private
Dataset/Schema/Record/Relation versions. Initialize an explicitly authorized
project-private model dataset and the [schema pack](config/schemas/story-planning.json)
through the existing preview/save tools. Nothing is initialized automatically.
This feature does not modify manuscripts or Canon. `story_chapter_context` reads
a bounded fixed graph scope, and `story_consistency_review` checks only explicit
comparable time/location/state assertions. External source aggregation, semantic
literary review and actual Chat host acceptance remain separate gates.
See the [design and boundaries](docs/design/story-planning.md).

### Runtime parity policy

The local private runtime may be used as a behavioral reference while public
features are developed. Reusable behavior is ported narrowly with synthetic tests;
private history and project content are never synchronized. See the
[capability matrix and publication boundary](docs/design/private-runtime-parity.md).
