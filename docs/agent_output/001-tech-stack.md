# 项目技术栈说明

本文档说明智能销售 Agent 重构项目计划采用的技术栈。当前项目已完成 FastAPI 骨架、MySQL 表结构与测试数据、SQLAlchemy 模型、Repository 层、SalesQueryService、销售 DTO/schemas、5 个 LangChain 工具、Agent Runtime、多轮记忆、同步聊天 API 和 SSE 流式聊天 API。认证、缓存等依赖会在对应阶段再引入。

## 核心语言与包管理

- Python 3.12：项目主语言。
- uv：项目依赖管理、虚拟环境管理和命令运行工具。

## Web 框架

- FastAPI：后端 API 框架，负责 HTTP 接口、依赖注入、请求校验和响应返回。
- Uvicorn：ASGI 应用服务器，用于本地启动和后续部署运行。
- StreamingResponse：FastAPI/Starlette 提供的流式响应能力，当前用于 `text/event-stream` SSE 输出。

当前启动入口：

```bash
uv run uvicorn app.main:app --reload
```

## 配置管理

- pydantic-settings：定义应用配置对象，支持从环境变量和 `.env` 读取配置。
- python-dotenv：辅助加载本地 `.env` 文件。

当前配置入口：

```text
app/core/config.py
```

## 数据库与 ORM

- SQLAlchemy Async：异步 ORM 和数据库访问层。
- MySQL：当前项目数据库，连接本机 `127.0.0.1:3306`。
- asyncmy：MySQL 异步驱动，已引入，用于 SQLAlchemy Async 连接 MySQL。
- aiosqlite：仅用于测试中的内存 SQLite 场景，不作为业务运行时数据源。
- Alembic：数据库迁移工具，后续用于管理表结构变更。

当前数据库相关文件：

```text
app/core/database.py
app/models/
app/repositories/
app/services/
app/schemas/
app/db/schema.sql
app/db/data.sql
```

数据库设计策略：

- 当前开发数据库使用本地 MySQL。
- 数据库连接通过根目录 `.env` 的 `DATABASE_URL` 配置。
- 集成测试中的 Service/Repository 行为测试可使用内存 SQLite，避免依赖本地 MySQL 状态。
- MySQL 初始化采用直接执行 `schema.sql` 和 `data.sql` 的方式，不再通过 Python seed 脚本导入。

## 项目分层

当前采用 FastAPI 分层架构：

```text
app/api/           # HTTP 接口层
app/core/          # 配置、数据库、安全、日志等基础设施
app/models/        # SQLAlchemy 数据库表映射类
app/schemas/       # Pydantic DTO、请求对象、响应对象
app/repositories/  # 数据访问封装
app/services/      # 业务逻辑和销售分析服务
app/tools/         # LangChain 工具
app/agent/         # Agent 编排、提示词、记忆、运行时；流式输出后续补齐
app/db/            # 数据库结构说明和测试数据初始化
```

## 测试技术栈

- pytest：测试框架。
- pytest-asyncio：异步测试支持。
- httpx：FastAPI 接口集成测试客户端。

当前集成测试：

```text
tests/integration/test_health.py
tests/integration/test_database_sql.py
tests/integration/test_model_mapping.py
tests/integration/test_sales_repositories.py
tests/integration/test_sales_query_service.py
tests/integration/test_sales_tools.py
tests/integration/test_agent_memory.py
tests/unit/test_agent_prompt.py
tests/integration/test_agent_api.py
tests/integration/test_agent_streaming.py
```

当前验证命令：

```bash
uv run python -m pytest tests\integration -v
```

## LangChain 工具与 Agent 技术栈

- LangChain：已引入，用于 `@tool(args_schema=...)` 创建销售分析工具。
- langchain-core：随 LangChain 引入，提供 BaseTool 等核心抽象。
- langchain-openai：已引入，用于通过 OpenAI 兼容接口接入 `.env` 中配置的模型。
- LangChain Agent runtime：当前使用 `thread_id` 标识会话，并以 MySQL `sa_chat_memory` 作为默认会话记忆来源。

当前使用位置：

```text
app/tools/
app/agent/
app/api/v1/endpoints/agent.py
```

Agent Runtime 策略：

- 使用 LangChain 官方推荐的 `create_agent(...)` 绑定 5 个销售工具。
- 使用 `init_chat_model(model_provider="openai", base_url=..., api_key=...)` 接入 OpenAI 兼容模型，默认读取 `.env` 中的 `OPENAI_MODEL`、`OPENAI_BASE_URL`、`OPENAI_API_KEY`。
- 使用 `config={"configurable": {"thread_id": session_id}, "recursion_limit": 10}` 标识会话并限制 Agent 循环步数。
- 使用 `sa_chat_memory` 表保存最近 20 条用户消息、关键工具结果和 AI 回复快照；每轮调用前从 MySQL 加载 user/assistant 历史作为上下文，测试中通过 fake agent 验证记忆链路，不调用真实 LLM。
- `checkpointer` 仅作为 runtime 可注入扩展点保留，默认不启用内存 checkpointer。
- 同步 API `POST /agent/chat` 返回完整回答、耗时、工具调用摘要和数据引用占位。
- 流式 API `POST /agent/chat/stream` 使用 SSE，事件类型包括 `token`、`tool`、`done`、`error`，事件数据统一使用 JSON。

## 认证与权限阶段计划技术栈

以下依赖会在用户认证与数据权限隔离阶段再引入：

- python-jose：JWT 编码和解码。
- passlib：密码哈希和校验。
- bcrypt：密码哈希算法支持。

计划使用位置：

```text
app/core/security.py
app/api/dependencies.py
app/api/v1/endpoints/auth.py
app/services/auth_service.py
```

## 缓存阶段计划技术栈

以下依赖会在 Redis 缓存阶段再引入：

- redis：Redis 客户端。

计划使用位置：

```text
app/services/cache_service.py
```

## 暂不采用的技术

- 前端框架：本轮先实现后端和 Agent，不开发前端页面。
- RAG 向量库：当前参考文献只是开发期资料，不作为运行时知识库；因此暂不引入 Chroma、FAISS、Pinecone。
- 自定义 LangGraph 工作流：当前不手写 StateGraph 工作流；除非后续流程编排明显复杂化，否则不提前引入自定义 LangGraph 图。
- 生产部署栈：暂不引入 Docker、Kubernetes、CI/CD、云监控。

## 当前已安装依赖

生产依赖：

```text
fastapi
uvicorn[standard]
pydantic-settings
python-dotenv
sqlalchemy[asyncio]
aiosqlite
alembic
asyncmy
langchain
langchain-openai
```

开发依赖：

```text
pytest
pytest-asyncio
httpx
```
