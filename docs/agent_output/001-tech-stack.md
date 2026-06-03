# 项目技术栈说明

本文档说明智能销售 Agent 重构项目计划采用的技术栈。当前项目处于 FastAPI 骨架初始化阶段，部分依赖已经引入，Agent、认证、缓存等依赖会在对应阶段再引入。

## 核心语言与包管理

- Python 3.12：项目主语言。
- uv：项目依赖管理、虚拟环境管理和命令运行工具。

## Web 框架

- FastAPI：后端 API 框架，负责 HTTP 接口、依赖注入、请求校验和响应返回。
- Uvicorn：ASGI 应用服务器，用于本地启动和后续部署运行。

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
- asyncmy：计划使用的 MySQL 异步驱动，实际连接 MySQL 前需要引入。
- aiosqlite：仅保留给测试或临时 SQLite 场景使用。
- Alembic：数据库迁移工具，后续用于管理表结构变更。

当前数据库相关文件：

```text
app/core/database.py
app/models/
app/db/schema.sql
app/db/seed.py
```

数据库设计策略：

- 当前开发数据库使用本地 MySQL。
- 数据库连接通过根目录 `.env` 的 `DATABASE_URL` 配置。
- 测试可继续使用内存 SQLite，避免依赖本地 MySQL 状态。

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
app/agent/         # Agent 编排、提示词、记忆、流式输出
app/db/            # 数据库结构说明和测试数据初始化
```

## 测试技术栈

- pytest：测试框架。
- pytest-asyncio：异步测试支持。
- httpx：FastAPI 接口集成测试客户端。

当前基础测试：

```text
tests/integration/test_health.py
tests/integration/test_database_seed.py
```

当前验证命令：

```bash
uv run python -m pytest tests\integration\test_health.py tests\integration\test_database_seed.py -v
```

## Agent 阶段计划技术栈

以下依赖尚未在当前阶段引入，会在实现 Agent 工具和运行时再加入：

- LangChain：Agent 编排和工具调用框架。
- langchain-core：核心消息、工具、Runnable 抽象。
- langchain-openai：OpenAI 兼容模型接入。

计划使用位置：

```text
app/tools/
app/agent/
```

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
- LangGraph：当前优先使用 LangChain tool-calling Agent；除非后续流程编排明显复杂化，否则不提前引入。
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
```

待引入数据库驱动：

```text
asyncmy
```

开发依赖：

```text
pytest
pytest-asyncio
httpx
```
