# Sales Agent

基于 FastAPI、SQLAlchemy Async、MySQL 和 LangChain 重构的智能销售数据分析 Agent。项目参考原 LangChain4j 智能销售 Agent 的业务设计、测试数据和工具粒度，用 Python 技术栈重新实现后端 API、销售分析工具、权限过滤、多轮会话记忆、流式输出、日志追踪和 token 成本控制。

## 当前能力

- 销售订单查询、销售额汇总、排行统计、趋势分析、图表数据生成、异常预警。
- 5 个 LangChain 工具：`query_sales_orders`、`calculate_sales_summary`、`analyze_sales_trend`、`generate_sales_chart`、`detect_sales_anomalies`。
- 同步聊天接口：`POST /agent/chat`。
- SSE 流式聊天接口：`POST /agent/chat/stream`。
- JWT 登录和权限过滤：销售员、销售主管、销售总监看到不同数据范围。
- MySQL 会话记忆持久化：`sa_chat_memory`。
- LangChain `SummarizationMiddleware` 消息摘要压缩，控制长会话 token 成本。
- 控制台日志追踪、traceId、工具调用日志和 token 成本估算。
- SQLAlchemy 表达式查询和 Pydantic 参数白名单校验，降低 SQL 注入风险。

## 技术栈

- Python 3.12
- uv
- FastAPI
- Uvicorn
- Pydantic Settings
- SQLAlchemy Async
- MySQL + asyncmy
- LangChain + langchain-openai
- PyJWT
- pytest + pytest-asyncio + httpx

## 项目结构

```text
app/
  api/            # API 路由、依赖注入
  agent/          # Agent runtime、prompt、memory、streaming
  core/           # 配置、数据库、安全、日志、异常、上下文
  db/             # schema.sql、data.sql
  models/         # SQLAlchemy 表映射
  repositories/   # 数据访问层
  schemas/        # Pydantic DTO、请求和响应对象
  services/       # 业务查询、统计、权限过滤
  tools/          # LangChain tools
docs/
  agent_output/   # 阶段性设计说明和结论
  plans/          # 项目计划书
  process/        # 代码编写过程记录
  specs/          # 项目 spec
tests/
  integration/
  unit/
```

## 快速开始

安装依赖：

```bash
uv sync
```

创建并检查根目录 `.env`：

```env
DATABASE_URL=mysql+asyncmy://root:<password>@127.0.0.1:3306/sales_agent
OPENAI_API_KEY=<your-api-key>
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=deepseek-v4-flash
OPENAI_STREAMING_MODEL=deepseek-v4-flash
AGENT_SUMMARY_MODEL=deepseek-v4-flash
JWT_SECRET_KEY=dev-secret-change-me-use-env-in-production
```

初始化数据库：

```bash
mysql -uroot -p -e "CREATE DATABASE IF NOT EXISTS sales_agent DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -uroot -p sales_agent < app/db/schema.sql
mysql -uroot -p sales_agent < app/db/data.sql
```

启动服务：

```bash
uv run uvicorn app.main:app --reload
```

## API 示例

登录获取 JWT：

```bash
curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"repId":2}'
```

调用同步 Agent：

```bash
curl -s -X POST "http://localhost:8000/agent/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"sessionId":"scenario-001","message":"上个月华东区的销售情况怎么样？"}'
```

调用流式 Agent：

```bash
curl -N -X POST "http://localhost:8000/agent/chat/stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"sessionId":"scenario-001","message":"按产品品类拆分一下"}'
```

流式接口事件类型：

- `token`：模型输出片段。
- `tool`：工具调用结果摘要。
- `done`：最终结果，包含 `sessionId`、`reply`、`durationMs`、`toolCalls`、`dataReferences`。
- `error`：稳定错误事件。

## 测试

运行全量测试：

```bash
uv run python -m pytest -v
```

运行集成测试：

```bash
uv run python -m pytest tests/integration -v
```

测试中可能使用 SQLite 内存库验证 Repository、Service 和 API 行为；业务运行时数据源仍是 `.env` 中配置的 MySQL。

## 与原 LangChain4j 项目的对比

| 维度 | 原 LangChain4j 项目 | 当前 Python 重构项目 |
| --- | --- | --- |
| 主语言 | Java | Python 3.12 |
| Web 框架 | Spring Boot 风格实现 | FastAPI |
| Agent 框架 | LangChain4j | LangChain |
| 工具粒度 | 销售查询、汇总、趋势、图表、异常预警等工具 | 对齐为 5 个 LangChain tools |
| DTO | Java DTO | Pydantic schemas |
| 数据访问 | Java Repository/Mapper 风格 | SQLAlchemy Async Repository |
| 数据库 | 参考项目数据结构 | MySQL，表结构和测试数据由 `schema.sql`、`data.sql` 初始化 |
| 权限模型 | 参考文献中的销售角色权限 | `SALES_REP`、`SALES_MANAGER`、`SALES_DIRECTOR`，在 Service 层过滤 |
| 会话记忆 | 参考项目中的多轮上下文能力 | MySQL `sa_chat_memory`，只保存 `user/assistant` 消息 |
| Token 控制 | 参考文献中的生产增强方向 | LangChain `SummarizationMiddleware` 摘要压缩，不使用 Redis 缓存 Agent 回答 |
| API 输出 | 参考项目接口语义 | FastAPI 同步 JSON + SSE 流式事件 |
| 测试方式 | 参考文献中的场景和测试数据 | pytest 单元测试和集成测试 |
| 参考文献使用方式 | 项目自身实现 | 仅作为开发期资料，按 `docs/reference/00_SUMMARY.md` 渐进加载 |

## 设计取舍

- 不缓存 Agent 最终回答。原因是自然语言问题、权限范围、日期和查询条件会让缓存 key 维度过大，命中率低；如果额外用 LLM 或 embedding 做语义匹配，可能反而增加 token 成本。
- 使用消息摘要压缩控制长会话上下文，而不是裁剪数据库全部历史。数据库最多保存最近 20 条 `user/assistant` 消息，摘要由 LangChain middleware 在模型上下文层处理。
- 工具层返回稳定、可读的文本或 `CHART_JSON`，由 Agent 组织最终自然语言回答。
- API 层不做业务兜底，业务边界尽量放在 service、tool、agent runtime 等对应层中。

## 文档入口

- `Agents.md`：后续 AI Agent 或开发协作者指南。
- `docs/plans/001-sales-agent-refactor-master-plan.md`：总计划书。
- `docs/agent_output/001-tech-stack.md`：技术栈说明。
- `docs/specs/`：阶段性规格文档。
- `docs/process/`：阶段性实现过程记录。
