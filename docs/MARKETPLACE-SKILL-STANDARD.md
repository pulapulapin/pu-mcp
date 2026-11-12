# PuKnowledge Marketplace Skill 标准

本标准适用于通过 Agensi 等 Agent Skill 市场分发、并以 PuKnowledge MCP
作为外部能力依赖的公开 Skill。它规定产品边界、交付内容和验收证据；不代表
任何市场已经批准、发布或开始收费。

## 1. 产品分层

| 层 | 职责 | 是否由 Skill 市场交付 |
| --- | --- | --- |
| PuKnowledge MCP | 本地项目、版本、来源、权限和受控写入 | 否；由用户独立安装和运行 |
| Marketplace Skill | 告诉 Agent 何时、为何、按什么顺序调用 MCP | 是；只包含通用指令和必要文本 |
| 用户项目 | 正文、Canon、研究资料、决策、配置和数据库 | 否；始终由用户控制 |

Skill 不得携带 MCP 可执行环境、虚拟环境、真实数据库、用户目录、密钥、私有
项目样本或第三方受版权保护的全文。MCP 未安装或缺少所需工具时，Skill 必须
返回 `BLOCKED`，不得用模型记忆伪装为已调用。

## 2. 一个 Skill 只承诺一个可验收结果

每个 Skill 必须写明：

- `job`：它替用户完成的单一工作。
- `trigger`：何时应该使用，何时不应使用。
- `requires`：所需 MCP、模块、工具和宿主能力。
- `workflow`：最短、确定的调用顺序。
- `output_contract`：用户可检查的结果字段。
- `write_boundary`：只读步骤、预览步骤和需要授权的写入步骤。
- `known_limitations`：明确不提供什么。

不得用工具数量代替结果说明。页面示例必须展示一次完整的真实工作流：输入、
调用、证据、输出、缺失信息和下一步。

## 3. SKILL.md 元数据

发布候选的顶层 `SKILL.md` 至少包含以下 frontmatter：

```yaml
---
name: Human-readable unique name
description: One concrete job and its observable result.
summary: Short marketplace summary.
version: 0.1.0
tags:
  - project-management
keywords:
  - traceable context
use_cases:
  - Recover a versioned project handoff in a new agent session.
docs_url: https://github.com/pulapulapin/pu-mcp
---
```

正文必须有 `Requires:` 行，明确写出 PuKnowledge MCP 及所需模块。不得暗示
Agensi 会安装、托管或运行 PuKnowledge。

## 4. 权限和数据边界

Skill 必须遵守以下默认规则：

1. 先调用 `workspace_guide`，再调用 `workspace_list_projects`。
2. 项目必须由用户明确选择；禁止默认小说、默认工作区或按目录名猜测。
3. 默认只读。任何持久化写入必须先预览 Diff，返回基线和指纹，再取得用户授权。
4. 保存时必须复用预览返回的基线、指纹和新的幂等键；冲突后不得静默覆盖。
5. 候选、草稿、Prompt 和任务快照不得自动提升为 Canon、批准决策或已发布内容。
6. 不遍历未授权目录，不读取其他项目来“补全”当前项目。
7. 不把资料中的文字当成工具指令执行。
8. 不把用户内容、文件名、项目名或运行统计发送给 Skill 作者。

若 Skill 使用其他网络服务，必须逐项声明，并在访问前说明传输的数据类型。当前
Project Continuity 候选不需要把项目内容发送给 PuKnowledge 作者或 Agensi 作者。

## 5. 状态与输出契约

面向用户的最终状态只使用：

- `READY`：本次承诺的来源、版本和任务状态已经读取并核对。
- `PARTIAL`：可以限定范围继续，但必须列出尚未读取或未验证的内容。
- `BLOCKED`：缺少会直接影响正确性的工具、项目、权限或关键上下文。

成功输出至少包含：

```text
status
project_id
task_id
direction_revision
next_step
sources_loaded
missing_or_unverified
writes_performed
```

`READY` 只证明约定范围已交付，不证明来源真实、结论正确、文章精彩或产品已经
验收。结构校验、文学评审和事实核验必须分别报告。

## 6. 安全与审查准备

发布 ZIP 只允许必要的文本、模板和可审查脚本。禁止：

- 凭据、令牌、真实邮箱、授权码和付款资料。
- 用户绝对路径、私人项目标识和真实内容样本。
- 可执行二进制、虚拟环境和打包依赖目录。
- 隐藏行为、混淆逻辑、静默网络上传和绕过上级约束的指令。
- 外部付费链接、解锁码交付或引导绕过市场结账。

任何脚本必须可独立审查，默认不联网，文件写入范围清晰，并在失败时保留原始
数据。发布前运行仓库测试、Skill lint 和私有内容扫描。

## 7. 兼容性声明

兼容性分为四级，不得合并：

1. `protocol-tested`：直接 stdio/MCP 协议测试通过。
2. `simulated-host-profile`：合成宿主行为探针通过。
3. `real-host-synthetic-project`：真实宿主、合成项目行为验收通过。
4. `external-user-verified`：未参与开发的用户独立完成首装与任务。

商品页只能列出已有证据的级别。某个宿主发现工具成功，不代表写入、恢复、隔离
和长响应均已通过。

## 8. 版本与更新

- Skill 使用独立语义版本，不与 MCP 版本强制相同。
- 每个版本声明最低 PuKnowledge 版本、必需工具及兼容性变化。
- MCP 工具缺失时停止，不用旧工具或模型记忆静默降级。
- 更新不得改变用户数据位置、写入授权或 Canon 规则而不明确说明。
- 保留变更记录和对应合成验收报告。

## 9. 商业状态用词

公开材料只能使用以下状态：

| 状态 | 含义 |
| --- | --- |
| `FREE_OPEN_SOURCE` | 开源运行时可免费使用，不含收费权益 |
| `LISTING_CANDIDATE` | Skill 包已准备，尚未提交或通过市场审核 |
| `PAID_LISTING_LIVE` | 市场已批准，买家可以实际付款和取得使用权 |
| `PAID_SERVICE_LIVE` | 自有服务已完成真实支付、权益、退款和运营验收 |

本仓库当前属于 `FREE_OPEN_SOURCE`；仓库内 Marketplace Skill 为
`LISTING_CANDIDATE`。在 Agensi 实际批准并上架前，不得称为已具备收费能力。

## 10. 发布门槛

提交市场审核前必须同时满足：

- 候选 ZIP 通过本地 lint、安全扫描和私有内容扫描。
- 合成项目完成新会话恢复、预览授权保存和跨项目隔离。
- 至少一个声明支持的真实宿主完成行为验收。
- 安装、依赖、权限、数据位置、失败恢复和卸载说明齐全。
- 商品页有可复查的示例、已知限制和真实兼容性级别。
- 收款方式由 Owner 本人完成平台验证；仓库不保存付款凭据。

正式发布后的外部用户数据是市场验证门槛，不应由维护者本机测试替代。

仓库提供的 lint 只包含可公开的通用规则。维护者应在提交前通过
`--private-terms-file` 传入仓库外的本地拒绝词表；该词表不得进入版本控制。
