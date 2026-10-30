# Changelog

## Unreleased

- Add optional longform candidate story graph read/preview/save, reusing private Knowledge datasets and atomic version commits.
- Report explicit dependency impact paths and stale endpoints without promoting candidates to Canon.
- Add synthetic 48-chapter and real stdio tests; chapter context and semantic continuity checks remain pending.
- Port generic fixed-version Prompt resolution, explicit writing-context recovery,
  manuscript/source anchors and neutral corpus indexing from the local behavioral
  reference, with synthetic tests only.

## 0.3.3

- 发布单一中性 MCP 入口 `pu-knowledge-workbench`。
- 提供可组合的 `core`、`fs` 和 `longform` 模块。
- 增加 `workspace_guide`、长文快照、结构化知识数据集以及桌面插件绑定流程。
- 公开仓库只保留通用代码、合成测试和可移植配置示例；本机数据库、业务资料、兼容桥与部署绑定不进入发布树。
