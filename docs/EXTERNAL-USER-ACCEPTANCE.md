# 外部用户首装验收

这份流程用于未参与 PuKnowledge 开发的人验证“能否独立安装并在真实 MCP 宿主中恢复长期任务”。全程只使用合成项目，不需要小说资料、账号订阅或现有 PuKnowledge 数据。

## 验收目标

- 15 分钟内完成安装和首次恢复；
- 安装包五档合成探针全部通过；
- 真实宿主能够发现工具、预览后保存、在新 Chat 精确恢复；
- 相同会话 ID 不能从另一个项目读取；
- 快照保持 `canon=false`、`approval_verified=false`。

协议探针通过但宿主配置失败应记为 `PARTIAL`，不能写成产品全面通过。额度不足或没有可用宿主记为 `NOT RUN`，不是功能失败。

## 1. 安装候选版本

```bash
git clone https://github.com/pulapulapin/pu-mcp.git
cd pu-mcp
git switch feat/story-planning
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/puknowledge-compat --profile all
```

最后一条命令应返回顶层 `state=PASS`，并列出五个通过档位。它是协议验收，不代替后面的真实宿主调用。

## 2. 一条命令准备宿主夹具

指定一个尚不存在的新目录：

```bash
.venv/bin/puknowledge-compat --prepare-host ~/Documents/puknowledge-host-acceptance
```

命令拒绝覆盖已有目录，返回可直接登记到 MCP 宿主的 `mcp.command`、`mcp.args` 和 `transport=stdio`。它只创建四个合成项目及配置，不创建数据库、不扫描其他目录：

- `alpha`、`beta`：普通长期任务；
- `story-alpha`、`story-beta`：长文任务。

把返回的 `command` 和完整 `args` 原样填入 Cursor、TRAE、Claude Code 或其他 MCP 宿主。连接成功后新建一个 Chat。

## 3. 在真实宿主中执行

先发送只读发现指令：

```text
只使用已连接的 PuKnowledge MCP 工具。调用 workspace_guide 和
workspace_list_projects，不要使用终端，不要写入。报告服务版本、已加载模块、
四个项目 ID，以及 story-alpha 的 workspace_interface。
```

预期：模块为 `core, fs, longform`，四个项目都可见，`story-alpha` 的接口为 `writing`。

再发送预览指令：

```text
只通过 PuKnowledge 工具，为 project=story-alpha、session_id=external-host-acceptance
预览一份写作交接快照，不要保存。快照内容固定为：
task=Verify external-host longform recovery.
summary=Synthetic external-user acceptance only.
next_step=Open a new Chat and recover this exact task.
task_context.task_id=EXTERNAL-HOST-001
task_context.stage=host-acceptance
task_context.state=active
task_context.direction_revision=1
调用 writing_preview_snapshot 后报告 baseline、preview_fingerprint、saved 和 canon。
```

确认返回 `baseline=0`、`saved=false`、`canon=false` 后，再明确发送：

```text
批准按刚才完全相同的预览保存一次，operation_key=external-host-acceptance-r1。
只能调用 writing_save_snapshot 一次。保存后报告 revision、canon 和
approval_verified；不要修改项目文件。
```

预期：`revision=1`、`canon=false`、`approval_verified=false`。

## 4. 新 Chat 恢复和隔离

关闭当前 Chat 或新建一个完全独立的 Chat，发送：

```text
只通过 PuKnowledge MCP 工具执行两次只读核对，不要使用终端：
1. writing_resume(project=story-alpha, session_id=external-host-acceptance)
2. writing_resume(project=story-beta, session_id=external-host-acceptance)
报告 Alpha 的 task_id、direction_revision、next_step；报告 Beta 是否明确拒绝或保持无任务，
并确认 Beta 响应中是否出现 Alpha 的任务内容。
```

预期：Alpha 精确恢复 `EXTERNAL-HOST-001`、方向版本 1 和指定下一步；Beta 明确返回指定会话不存在且不回退，或保持未分配，并且不包含 Alpha 内容。

## 5. 回报模板

```text
操作系统与版本：
Python版本：
宿主与版本：
从开始到首次恢复耗时：
安装：PASS / FAIL
五档协议探针：PASS / FAIL
宿主工具发现：PASS / FAIL
预览与单次保存：PASS / FAIL
新Chat恢复：PASS / FAIL
跨项目隔离：PASS / FAIL
是否看到真实项目或私人内容：YES / NO
最困惑的一步：
最终结论：PASS / PARTIAL / FAIL / NOT RUN
```

测试结束后可以把整个 `puknowledge-host-acceptance` 文件夹移到废纸篓；其中只有合成夹具和本次验收产生的本地数据库。不要删除任何自己原有的 PuKnowledge 目录。
