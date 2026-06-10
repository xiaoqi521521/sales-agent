# 架构与模块边界规格说明

## 1. 总体架构

项目采用 FastAPI 分层架构，核心调用链如下：

```text
HTTP API
  -> Agent Runtime
  -> LangChain Tools
  -> Service
  -> Repository
  -> SQLAlchemy Model
  -> MySQL
```

参考文献只作为开发期知识库，不进入业务运行时。运行时依赖项目代码、数据库和 `.env` 配置。

## 2. LangChain4j 到 Python 技术映射

| 参考项目概念 | Python 项目实现 |
| --- | --- |
| Spring Boot Controller | FastAPI endpoint |
| LangChain4j Agent 接口 | `app/agent/runtime.py` 中的 `SalesAgentRuntime` |
| LangChain4j Tool | `app/tools/` 下的 LangChain `@tool(args_schema=...)` |
| Java DTO | `app/schemas/` 下的 Pydantic schema |
| JPA Entity | `app/models/` 下的 SQLAlchemy model |
| Repository 接口 | `app/repositories/` 下的查询封装类 |
| Service 查询封装 | `app/services/sales_query_service.py` |
| ChatMemory | `app/agent/memory.py` + `sa_chat_memory` |
| 用户上下文 | `app/core/auth_context.py` 中的 `CurrentUser` |

## 3. 模块职责

### `app/api`

负责 HTTP 协议、路由挂载、请求体验证、依赖注入和响应模型绑定。

约束：

- 不写销售业务查询。
- 不直接访问 Repository。
- 认证通过依赖注入解析当前用户。
- Agent 接口只调用 `SalesAgentRuntime`。

### `app/agent`

负责构建系统提示词、组装 LangChain Agent、绑定工具、处理多轮记忆和流式输出。

约束：

- 不直接查询数据库中的销售业务表。
- 只通过 Tool 获取销售数据。
- 会话记忆可以访问 `sa_chat_memory`，用于保存 user/tool/assistant 消息。

### `app/tools`

负责把销售业务能力封装为 LangChain tools。

当前 5 个工具为：

- `query_sales_data`
- `calculate_sales_summary`
- `analyze_sales_trend`
- `generate_chart_data`
- `detect_sales_anomalies`

约束：

- 工具参数使用 Pydantic schema 校验。
- 工具不直接拼接 SQL。
- 工具调用 Service 层，继承 Service 层权限过滤。
- 文本类工具返回可读摘要；图表工具返回 `CHART_JSON:{...}`。

### `app/services`

负责销售业务规则、聚合分析、趋势计算、异常判断和权限过滤。

约束：

- Service 是权限过滤主边界。
- Service 接收 `CurrentUser` 后，根据角色收缩查询范围。
- Service 不负责 HTTP 状态码和响应协议。

### `app/repositories`

负责数据库访问封装。

约束：

- 使用 SQLAlchemy 表达式和参数绑定。
- 不拼接不可信 SQL。
- 不包含角色权限判断。
- 不依赖 FastAPI 请求上下文。

### `app/models`

负责数据库表映射，保持与 `app/db/schema.sql` 中的表结构对齐。

当前核心模型：

- `SalesRegion` -> `sa_sales_region`
- `SalesRep` -> `sa_sales_rep`
- `Product` -> `sa_product`
- `SalesOrder` -> `sa_sales_order`
- `ChatMemory` -> `sa_chat_memory`

### `app/schemas`

负责 API 请求响应 DTO 和服务间结构化数据对象。

约束：

- 对外字段优先使用当前 API 契约中的 camelCase，例如 `sessionId`、`durationMs`。
- Python 内部字段保持 snake_case，通过 Pydantic alias 对齐外部字段。

### `app/core`

负责配置、数据库连接、安全能力和认证上下文。

关键文件：

- `config.py`：读取项目根目录 `.env`。
- `database.py`：创建异步数据库 engine 和 session。
- `security.py`：JWT 创建与解析。
- `auth_context.py`：当前用户上下文。

## 4. 会话记忆边界

会话记忆持久化在 MySQL `sa_chat_memory` 表。

保存内容：

```text
user -> tool -> assistant
```

发送给大模型的上下文只包含 `user` 和 `assistant`。`tool` 消息用于本轮追踪、响应摘要和 API 返回，不进入长期会话记忆。

## 5. 错误与增强边界

在 Phase 0 规划语境中，认证、流式输出和消息摘要压缩都被定义为后续增强能力，不阻塞基础 Agent 跑通。

当前实现状态备注：认证与流式输出已经在后续阶段落地；统一 API envelope、统一错误码、请求日志、token 成本统计和消息摘要压缩仍属于生产化增强内容。

## 6. 验证方式

架构边界应通过以下方式验证：

- API 层测试只通过 HTTP 调用验证行为。
- Service 与 Repository 测试可使用内存 SQLite。
- Tool 测试应能不依赖真实 Agent 独立运行。
- Agent 测试可使用 fake model 或 mock agent factory 验证工具绑定与记忆链路。
- 权限测试应覆盖销售员、主管、总监三类角色。
