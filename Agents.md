# Agents.md

本文档面向后续参与本项目的 AI Agent 或开发协作者，说明如何在有限上下文中继续推进 `sales-agent` 项目。

## 项目定位

本项目是基于原 LangChain4j 智能销售 Agent 参考项目重构而来的 Python 版本。目标不是逐字翻译旧项目，而是在保留业务能力、测试数据和核心交互粒度的前提下，使用 FastAPI、SQLAlchemy Async、MySQL 和 LangChain 重建一个可运行、可测试、可逐步增强的销售数据分析 Agent。

## 必读顺序

优先按以下顺序加载上下文，避免一次性读取过多参考文献：

1. `README.md`：了解项目用途、运行方式和新旧项目差异。
2. `docs/plans/001-sales-agent-refactor-master-plan.md`：了解整体阶段计划。
3. `docs/agent_output/001-tech-stack.md`：了解当前技术栈。
4. `docs/specs/002-architecture-and-module-boundaries.md`：了解模块边界。
5. `docs/reference/00_SUMMARY.md`：只作为参考文献索引，按需加载原文。
6. `docs/process/`：查看已完成阶段的实现过程记录。

`docs/reference/` 已被放入 `.gitignore`，本地可能存在但不一定在远程仓库中。需要参考旧项目实现时，先读 `00_SUMMARY.md`，再按编号打开对应参考文献。

## 当前架构边界

- `app/api/`：HTTP 协议层，只负责请求响应、依赖注入和路由。
- `app/core/`：配置、数据库、安全、日志、异常、请求上下文等基础设施。
- `app/models/`：SQLAlchemy 数据库表映射。
- `app/schemas/`：Pydantic DTO、请求对象、响应对象。
- `app/repositories/`：数据库访问封装，使用 SQLAlchemy 表达式和参数绑定。
- `app/services/`：业务查询、统计、权限过滤和分析逻辑。
- `app/tools/`：LangChain tools，调用 service 层，不直接访问数据库。
- `app/agent/`：Agent prompt、runtime、会话记忆、SSE 事件格式。
- `app/db/`：MySQL 表结构和测试数据 SQL。
- `tests/`：单元测试和集成测试。

## 关键约束

- API 层不写业务查询。
- Tool 层不直接访问数据库。
- Service 层是业务规则和权限过滤的主要边界。
- Repository 层不得拼接不可信 SQL 字符串。
- Agent 只能通过工具访问销售数据。
- Runtime 模型只能来自配置文件，不允许通过构造参数传入其它模型。
- 会话记忆持久化到 MySQL `sa_chat_memory`，只保存 `user/assistant` 消息，不保存 `tool` 消息。
- Token 成本控制采用 LangChain 官方 `SummarizationMiddleware`，不使用 Redis 缓存 Agent 最终回答。

## 配置与模型

根目录 `.env` 负责运行时配置。常用配置项：

```env
DATABASE_URL=mysql+asyncmy://root:<password>@127.0.0.1:3306/sales_agent
OPENAI_API_KEY=<your-api-key>
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=deepseek-v4-flash
OPENAI_STREAMING_MODEL=deepseek-v4-flash
AGENT_SUMMARY_MODEL=deepseek-v4-flash
```

虽然配置项名沿用 OpenAI 兼容接口，但当前默认接入阿里云百炼兼容模式。

## 常用命令

安装依赖：

```bash
uv sync
```

启动服务：

```bash
uv run uvicorn app.main:app --reload
```

运行全量测试：

```bash
uv run python -m pytest -v
```

运行重点集成测试：

```bash
uv run python -m pytest tests/integration -v
```

## 数据库初始化

MySQL 表结构和测试数据位于：

```text
app/db/schema.sql
app/db/data.sql
```

优先直接导入 SQL 文件，不再通过 Python seed 脚本绕行。

## 开发流程建议

1. 修改前先用 `rg` 搜索相关调用点。
2. 涉及行为变更时先补测试。
3. 修改生产代码时保持分层边界，不为测试在生产代码中增加兼容分支。
4. 完成后运行相关测试，再运行全量测试。
5. 若更新功能边界，同步更新 `docs/plans/`、`docs/specs/` 或 `docs/process/`。

## 已知设计取舍

- SQLite 只用于测试中的内存数据库场景，不是业务运行时数据源。
- `agent_factory` 是 Runtime 的可替换组装边界，保留用于测试和未来扩展。
- `checkpointer` 目前只是预留扩展点，默认不启用内存 checkpointer。
- 目前不做前端页面、不做 RAG 向量库、不做 Redis Agent 回答缓存。
