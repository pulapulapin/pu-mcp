# Architecture

PuKnowledge 由三层组成：MCP 协议层负责工具注册与输入校验；服务层负责项目范围、版本和证据规则；SQLite 与显式许可目录负责持久化数据。HTTP 与 MCP 入口复用同一服务层。

能力采用固定基础 `core` + 按需扩展；公开扩展为 `fs` 和 `longform`。具体题材或规则体系通过领域数据包表达，详见[基础与扩展架构](EXTENSION-ARCHITECTURE.md)。

公开发行只挂载 `core`、`fs`、`longform`。模块决定工具表面，项目的 `domain` 决定业务语义。底层不会把某种题材、产品或规则体系硬编码为默认项目。

本地 stdio 和远程 HTTPS 是部署方式，不是两套数据库。多个入口只有在指向同一配置和 `data_dir` 时才共享数据。客户端缓存工具定义时，应重新加载连接后再验收。
