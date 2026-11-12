# 宿主兼容验证

PuKnowledge 可以被不同 MCP 宿主启动，但“服务符合 MCP 协议”和“某个宿主中的真实用户体验通过”是两个不同验收层。

当 Claude Code、Cursor 或其他目标宿主暂时不可用时，可以使用仓库提供的合成兼容探针，先验证公开服务本身的基础工作流：

```bash
puknowledge-compat --profile all
```

也可以单独执行一个档位：

```bash
puknowledge-compat --profile stdio-basic
puknowledge-compat --profile tools-only
puknowledge-compat --profile bounded-response --response-budget 12000
puknowledge-compat --profile cached-tools
```

## 四种档位

| 档位 | 主要验证 |
| --- | --- |
| `stdio-basic` | 初始化握手、工具与参数结构发现、项目发现、任务恢复、预览/保存、进程重启恢复、项目隔离 |
| `tools-only` | 只依赖 MCP tools，不要求宿主支持 prompts、resources 或专用 App |
| `bounded-response` | 记录工具响应字节数，并检查任务必需响应是否落在指定预算内 |
| `cached-tools` | 服务模块改变后工具清单发生变化，证明沿用旧工具缓存会失真，客户端应刷新发现结果 |

前三种档位还会通过 `fs` 模块列出并按 SHA-256 指纹读取一个合成文件。所有保存都发生在系统临时目录中的合成 SQLite 数据库；命令不接受真实项目路径，也不会读取用户现有 PuKnowledge 配置。

## 报告怎么读

成功报告的顶层状态是 `PASS`，并固定包含：

```json
{
  "state": "PASS",
  "simulated": true,
  "real_host_verified": false
}
```

`PASS` 证明当前安装的公开 PuKnowledge 入口可以完成探针列出的协议流程。它不能证明：

- Claude Code、Cursor 或其他真实宿主已经安装并成功连接；
- 宿主 UI、授权、OAuth、工具确认弹窗或长内容呈现符合预期；
- 宿主所用模型会在正确时机选择正确工具；
- 某个真实项目的恢复内容、创作质量或业务结果已经通过。

真实宿主可用后，仍应在不含私人内容的验收项目中重复：工具发现、明确选项目、恢复任务、读取准确来源、预览并保存、重开会话恢复、交叉项目拒绝。只有这些行为实际发生，才能把该宿主标记为已验收。

## 为什么仍然有价值

探针能把问题分层。如果探针失败，优先修复服务端入口、工具定义、版本恢复、响应大小或隔离逻辑；如果探针通过而真实宿主失败，问题范围可收窄到宿主配置、缓存、权限、UI 或模型工具选择。这样不需要在目标客户端不可用时停止产品验证，也不会把模拟证据夸大成实机证据。
