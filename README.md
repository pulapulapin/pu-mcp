# PuKnowledge

**面向长期研究与创作项目的、可追溯 AI 工作上下文与证据管理 MCP。**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

PuKnowledge 把聊天模型作为推理入口，把本地 MCP 作为可核对的工作台。任务方向、来源版本、证据引用、结构化知识和长文快照保存在用户指定的本地目录，换聊天窗口或 MCP 客户端后仍可按明确项目恢复。

## 它解决什么问题

普通聊天适合完成一次任务，却很难长期维护一个不断变化的项目：新会话需要重新解释背景，模型可能把旧方案当成当前决定，把候选内容当成正式事实，或者给出无法追溯来源的结论。

PuKnowledge 在模型之外保存项目状态，让 Agent 每次先核对再继续工作：

| 长期项目中的常见问题 | PuKnowledge 提供的帮助 |
| --- | --- |
| 换一个聊天窗口后，需要重新讲解整个项目 | 恢复当前任务、阶段、下一步和准确版本 |
| 历史方案、候选内容和正式决定混在一起 | 分开保存状态、来源、版本及权威边界 |
| 研究结论无法回答“依据是什么” | 记录来源、引文、指纹和证据关系 |
| 大纲或技术方案修改后，不知道影响哪里 | 通过结构化关系查询相关对象和候选影响 |
| Agent 直接写入导致误覆盖 | 先预览 Diff，再按基线、指纹和幂等键保存 |
| 多个项目共用一个 Agent，资料可能串线 | 显式选择项目，并限制项目私有数据的读取范围 |

### 一个典型使用过程

例如，一位作者在不同聊天中依次讨论世界观、人物、卷纲和正文。PuKnowledge 不替作者决定剧情，也不自动写小说；它负责告诉新会话：当前写到哪里、哪些内容已经批准、哪些只是候选、相关资料来自哪个版本，以及本次修改可能关联哪些章节。研究和产品项目使用的是同一套机制。

更多具体案例、适用环境和价值验证标准见[产品价值与使用场景](docs/PRODUCT-VALUE.md)。

## 可以在哪里使用

PuKnowledge 是 MCP 服务，不绑定某一个聊天产品。本地 `stdio` 入口可供支持 MCP 的桌面 Agent 或 IDE 启动；HTTP 入口可用于受保护的远程部署或自建应用。不同宿主的工具发现、授权和 UI 行为可能不同，因此“协议兼容”不等于已经完成宿主验收。

- 开发运行版已完成真实使用验证：当前本地 ChatGPT/Codex 插件环境；公开发行包仍需独立黑盒复验。
- 公开 `0.3.3` 代码已用合成项目完成 Cursor、TRAE 和 Claude Code CLI 2.1.311（第三方模型）的真实宿主工具验收；不代表真实业务项目、官方 Anthropic 模型或所有版本均已通过。
- 仍需逐项验收：Codex CLI/IDE、Kimi Code、VS Code Agent 模式及其他宿主。
- 可基于现有接口开发：独立小说/研究工作台、只读状态面板和自动检查任务。
- 尚不适合：未经鉴权的公网服务、多租户团队 SaaS，以及依赖本机文件却没有本地执行能力的纯网页客户端。

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
.venv/bin/pu-knowledge-workbench \
  --config ~/.config/puknowledge/workspace.json \
  --init-workspace /absolute/path/to/your/project \
  --project-id my-project \
  --label "My Project" \
  --domain research \
  --enable-fs
.venv/bin/pu-knowledge-workbench \
  --config ~/.config/puknowledge/workspace.json \
  --doctor
```

初始化只登记一个已经存在的目录并创建权限为当前用户可读写的配置文件；不会创建数据库、扫描项目内容或修改项目。`--doctor` 只读检查配置、路径、权限和已有 SQLite 的完整性，返回 `READY` 或 `BLOCKED`，但不能代替 MCP 宿主中的真实调用验收。

如果暂时无法运行 Claude Code、Cursor 等目标宿主，可以先执行公开的合成兼容探针：

```bash
.venv/bin/puknowledge-compat --profile all
```

探针会在临时目录中启动真实 MCP 服务，使用合成项目检查握手、工具发现、预览/保存、进程重启恢复、只读文件、项目隔离、响应预算和工具缓存变化。报告始终包含 `simulated=true` 与 `real_host_verified=false`；通过只代表协议工作流成立，不能替代真实宿主验收。范围、四种模拟档位和判定方式见[宿主兼容验证](docs/HOST-COMPATIBILITY.md)。

如需手工配置，可复制 `config/workspace.example.json`。本机配置不应提交；相对路径以配置文件所在目录为基准。

当前初始化命令创建的是通用 `task` 工作区，适合研究、产品和普通长期项目；它不会猜测小说结构或自动启用 `longform`。长篇项目仍应按已有项目格式和明确配置接入。

## MCP 配置

```json
{
  "mcpServers": {
    "pu-knowledge-workbench": {
      "command": "/absolute/path/to/pu-mcp/.venv/bin/pu-knowledge-workbench",
      "args": [
        "--config",
        "~/.config/puknowledge/workspace.json"
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

With `longform` enabled, `story_plan_bootstrap` returns and previews the exact
supported Schema Pack without saving it. `story_plan_get`, `story_plan_preview`
and `story_plan_save` manage a bounded candidate graph using existing private
Dataset/Schema/Record/Relation versions. Initialization still requires a
separately authorized `schema_save`; nothing is initialized automatically.
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
