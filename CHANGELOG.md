# Changelog

## Unreleased

- Record synthetic-project real-host acceptance on Cursor, TRAE and Claude Code
  CLI 2.1.311 with a third-party model: tool discovery, preview/save, new-session
  recovery and cross-project rejection passed. Kimi Code was not run due to account
  quota and is not reported as a failure.
- Add `puknowledge-compat`, a synthetic stdio host probe covering initialization,
  tool/schema discovery, preview/save, restart recovery, bounded file reads,
  project isolation, response budgets and stale tool caches. Reports always mark
  simulated evidence separately from real-host verification.
- Fix `fs_read_file` to honor its published optional `review_items` argument and
  return quote anchors against the full fingerprint-verified file.
- Add explicit `--init-workspace` onboarding and read-only `--doctor` checks.
  Initialization refuses overwrite, records one existing generic task workspace and
  leaves project content/storage untouched; doctor reports READY/BLOCKED for config,
  paths and existing SQLite integrity without creating a database.
- Add read-only `project_storage_get` and `project_storage_preview` tools that
  calculate a project-local `.puknowledge/workspace.sqlite3` target, project-owned
  migration closure and global dependencies without copying data or changing routing.
- Add exact-preview `project_storage_shadow_copy` and read-only
  `project_storage_verify`; project rows and pinned research-source dependencies must
  match normalized table fingerprints, SQLite integrity and foreign-key checks before
  a shadow copy succeeds. Runtime routing remains unchanged.
- Add explicit `project_stores` shadow/active bindings, atomic sync with preserved
  rollback files, and project-aware routing for drafts, snapshots, private datasets,
  story graphs and evidence. Global dataset replicas are read-only; shared books and
  unscoped global operations remain on the central store.
- Block full legacy-to-project sync after activation; verification treats central
  project rows as a rollback baseline so expected post-cutover divergence is not
  misreported as database corruption.
- Add read-only `story_plan_bootstrap` to return the exact supported Schema Pack,
  a real schema preview fingerprint and save arguments; incompatible nonempty
  datasets are blocked and no schema is saved automatically.
- Add optional longform candidate story graph read/preview/save, reusing private Knowledge datasets and atomic version commits.
- Report explicit dependency impact paths and stale endpoints without promoting candidates to Canon.
- Add version-pinned chapter graph context and conservative time/location/state
  consistency findings with explicit insufficient-evidence results.
- Add synthetic 48-chapter, package-manifest and real stdio tests; external-source
  aggregation and literary review remain separate future work.
- Port generic fixed-version Prompt resolution, explicit writing-context recovery,
  manuscript/source anchors and neutral corpus indexing from the local behavioral
  reference, with synthetic tests only.

## 0.3.3

- 发布单一中性 MCP 入口 `pu-knowledge-workbench`。
- 提供可组合的 `core`、`fs` 和 `longform` 模块。
- 增加 `workspace_guide`、长文快照、结构化知识数据集以及桌面插件绑定流程。
- 公开仓库只保留通用代码、合成测试和可移植配置示例；本机数据库、业务资料、兼容桥与部署绑定不进入发布树。
