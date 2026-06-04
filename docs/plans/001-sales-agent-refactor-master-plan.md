# 智能销售 Agent 重构总体计划书

> **For agentic workers:** 后续执行本计划时，每个阶段应拆成独立 spec 或实施计划，并按任务逐步加载 `docs/reference/00_SUMMARY.md` 中标明的参考文献。实现阶段优先使用 `fastapi-templates` 的 FastAPI 分层结构，并在涉及 LangChain Agent、RAG、LangGraph 或测试时加载对应技能。

**目标：** 基于 `docs/reference/` 中的 LangChain4j 智能销售 Agent 参考文献，用 Python、FastAPI、SQLAlchemy 和 LangChain 重建一个可运行、可测试、可逐步增强的智能销售数据分析 Agent。

**架构：** 后端采用 FastAPI 分层架构，API 层只处理协议与依赖注入，Service 层承载业务查询与分析，Repository 层封装数据库访问，LangChain Tools 调用 Service 层能力，Agent 层负责工具编排、多轮对话和最终回答。参考文献只作为开发期资料库，不进入业务运行时。

**Tech Stack：** Python 3.12、FastAPI、Uvicorn、Pydantic Settings、SQLAlchemy Async、MySQL、asyncmy、Alembic、LangChain、pytest、pytest-asyncio、httpx、可选 Redis。SQLite 仅用于测试中的内存数据库场景。

---

## 一、范围说明

### 本轮重构包含

- FastAPI 项目结构重建。
- 销售业务数据库模型与测试数据初始化。
- 销售查询、统计排名、趋势分析、图表数据、异常预警服务。
- 5 个 LangChain 工具。
- 智能销售 Agent 同步接口。
- 多轮会话记忆。
- 流式输出接口。
- 用户认证、角色权限与数据隔离。
- Redis 缓存、日志追踪、token 成本记录、SQL 注入防护。
- 单元测试、服务测试、API 集成测试和核心场景端到端测试。

### 本轮重构不包含

- 前端页面开发。
- 真实企业数据库接入。
- 多租户 SaaS 管理后台。
- 复杂 BI 报表系统。
- 生产 Kubernetes、CI/CD、云监控部署。

---

## 二、参考文献加载策略

常驻加载：

- `docs/reference/00_SUMMARY.md`

按阶段加载：

- 项目全貌：`01`、`02`、`06`、`15`
- 数据库与基础数据：`04`、`05`、`07`、`08`
- 查询与统计工具：`08`、`09`、`10`、`11`、`12`
- 图表与预警工具：`09`、`13`、`14`、`21`
- Agent 与 API：`15`、`16`、`17`、`18`
- 测试场景：`17`、`19`、`20`、`21`
- 生产增强：`22`、`23`、`24`、`25`、`26`

加载原则：

- 每个阶段开始前只加载该阶段相关参考文献。
- 摘要能回答的问题不打开原文。
- 需要字段、参数、DTO、代码结构、测试样例时再打开原文。
- 如果阶段之间出现依赖缺口，优先加载上游阶段参考文献，而不是全量读取。

---

## 三、目标目录结构

```text
sales-agent/
  app/
    main.py
    api/
      dependencies.py
      v1/
        router.py
        endpoints/
          health.py
          auth.py
          agent.py
          sales.py
    core/
      config.py
      database.py
      errors.py
      logging.py
      security.py
      context.py
    models/
      base.py
      sales_region.py
      sales_rep.py
      product.py
      sales_order.py
      chat_memory.py
      user.py
    schemas/
      auth.py
      agent.py
      sales.py
      chart.py
      anomaly.py
      common.py
    repositories/
      base_repository.py
      sales_region_repository.py
      sales_rep_repository.py
      product_repository.py
      sales_order_repository.py
      chat_memory_repository.py
      user_repository.py
    services/
      sales_query_service.py
      chart_service.py
      anomaly_service.py
      auth_service.py
      cache_service.py
      token_usage_service.py
    tools/
      sales_query_tool.py
      sales_summary_tool.py
      sales_trend_tool.py
      chart_generator_tool.py
      anomaly_detection_tool.py
      registry.py
    agent/
      prompts.py
      runtime.py
      memory.py
      streaming.py
    db/
      schema.sql
      data.sql
  tests/
    conftest.py
    unit/
    integration/
    e2e/
  docs/
    reference/
    specs/
    plans/
  pyproject.toml
```

---

## 四、阶段计划

### Phase 0：重构准备与规格冻结

**目标：** 把参考文献转化为本项目自己的 spec，明确 Python 版实现范围。

**加载参考：** `00_SUMMARY.md`、`01`、`02`、`06`、`15`

**产出文件：**

- `docs/specs/001-project-blueprint.md`
- `docs/specs/002-architecture-and-module-boundaries.md`
- `docs/specs/003-api-contract.md`

**任务：**

- [ ] 明确 Python 版项目目标、能力边界和不做事项。
- [ ] 定义 LangChain4j 到 LangChain/FastAPI 的映射关系。
- [ ] 确定 API 路径、请求响应结构、错误返回格式。
- [x] 确定开发阶段默认数据库为本地 MySQL，测试中可使用内存 SQLite 验证 Service/Repository 行为。
- [ ] 确定认证、缓存、流式输出作为后续增强阶段接入，不阻塞基础 Agent 跑通。

**验收：**

- `docs/specs/` 下至少有项目蓝图、架构边界、API 契约三份文档。
- 每份 spec 能回答“做什么、不做什么、依赖什么、如何验证”。

---

### Phase 1：FastAPI 项目骨架

**目标：** 建立生产化 FastAPI 基础结构，替换根目录的临时 `main.py`。

**加载参考：** `06`

**主要文件：**

- `app/main.py`
- `app/core/config.py`
- `app/core/errors.py`
- `app/core/logging.py`
- `app/api/v1/router.py`
- `app/api/v1/endpoints/health.py`
- `tests/conftest.py`
- `tests/integration/test_health.py`
- `pyproject.toml`

**任务：**

- [x] 增加应用包结构 `app/`。
- [x] 增加配置类，读取 `.env`，提供 `APP_NAME`、`API_V1_PREFIX`、`DATABASE_URL`、`OPENAI_API_KEY` 等配置。
- [x] 增加健康检查接口 `GET /api/v1/health`。
- [ ] 增加统一异常响应模型。
- [x] 配置测试客户端和基础集成测试。
- [ ] 移除或保留根目录 `main.py` 作为兼容入口，实际应用入口迁移到 `app/main.py`。

**验收命令：**

```bash
uv run pytest tests/integration/test_health.py -v
uv run uvicorn app.main:app --reload
```

**完成标准：**

- 健康检查返回应用名、版本、状态。
- 测试客户端能不依赖真实外部服务运行。
- 应用入口清晰，后续 API 都挂载到 `/api/v1`。

---

### Phase 2：数据库模型、迁移与测试数据

**目标：** 重建销售业务数据模型，并提供稳定测试数据。

**加载参考：** `04`、`05`、`07`

**主要文件：**

- `app/core/database.py`
- `app/models/base.py`
- `app/models/sales_region.py`
- `app/models/sales_rep.py`
- `app/models/product.py`
- `app/models/sales_order.py`
- `app/db/schema.sql`
- `app/db/data.sql`
- `tests/integration/test_database_sql.py`
- `tests/integration/test_model_mapping.py`
- `tests/integration/test_sales_repositories.py`

**任务：**

- [x] 实现异步 SQLAlchemy engine、session dependency 和 Base。
- [x] 建立 `sa_sales_region`、`sa_sales_rep`、`sa_product`、`sa_sales_order` 模型。
- [x] 保留参考文献中的核心字段、默认值和索引意图；ORM 不额外声明参考 DDL 中不存在的外键约束。
- [x] 使用 `schema.sql` 和 `data.sql` 直接初始化 MySQL 表结构与测试数据。
- [x] 为测试环境提供内存 SQLite 数据库，验证模型、Repository 和 Service 行为。

**验收命令：**

```bash
uv run python -m pytest tests/integration/test_database_sql.py tests/integration/test_model_mapping.py tests/integration/test_sales_repositories.py -v
```

**完成标准：**

- 数据库表能创建。
- SQL 导入后四类核心数据均存在。
- 订单数据覆盖多大区、多销售员、多产品、多月份和异常场景。

---

### Phase 3：Repository 与 SalesQueryService

**目标：** 建立统一查询服务，避免工具层直接拼接数据库查询。

**加载参考：** `08`、必要时回看 `04`、`07`

**主要文件：**

- `app/repositories/base_repository.py`
- `app/repositories/sales_region_repository.py`
- `app/repositories/sales_rep_repository.py`
- `app/repositories/product_repository.py`
- `app/repositories/sales_order_repository.py`
- `app/schemas/sales.py`
- `app/services/sales_query_service.py`
- `tests/integration/test_sales_query_service.py`
- `tests/integration/test_sales_repositories.py`

**任务：**

- [x] 定义销售 DTO/schemas，并与参考项目 `docs/reference/DTO` 中的 DTO 字段语义对齐。
- [x] 实现订单摘要查询。
- [x] 实现销售额汇总。
- [x] 实现按大区、销售员、产品的排名。
- [x] 实现增长率计算和月度趋势基础查询。
- [x] 保证所有查询使用 SQLAlchemy 表达式和参数绑定，不拼接不可信 SQL。
- [ ] 后续工具层如需要更复杂的组合过滤、客单价、同比/环比完整周期计算，可在 Service 层继续扩展。

**验收命令：**

```bash
uv run python -m pytest tests/integration/test_sales_query_service.py tests/integration/test_sales_repositories.py -v
```

**完成标准：**

- Service 层能覆盖 5 个工具所需的基础数据能力。
- 空结果返回结构化空数据，不抛不可控异常。
- 所有过滤条件可组合使用。

---

### Phase 4：5 个 LangChain 工具

**目标：** 将销售分析能力封装为可被 Agent 调用的 LangChain tools。

**加载参考：** `09`、`10`、`11`、`12`、`13`、`14`

**主要文件：**

- `app/tools/sales_query_tool.py`
- `app/tools/sales_summary_tool.py`
- `app/tools/sales_trend_tool.py`
- `app/tools/chart_generator_tool.py`
- `app/tools/anomaly_detection_tool.py`
- `app/tools/schemas.py`
- `app/tools/formatting.py`
- `app/tools/registry.py`
- `tests/integration/test_sales_tools.py`

**任务：**

- [x] 使用 LangChain 官方推荐的 `@tool(args_schema=...)` 创建工具，参数 schema 使用 Pydantic。
- [x] 实现销售数据查询工具。
- [x] 实现统计汇总与排名工具。
- [x] 实现同比环比与趋势分析工具。
- [x] 实现 ECharts 数据生成工具。
- [x] 实现异常数据告警工具。
- [x] 为每个工具编写明确 description，覆盖业务关键词和适用边界。
- [x] 文本类工具返回结构化可读文本，图表工具返回 `CHART_JSON:{...}`，与参考文献返回设计对齐。
- [x] 通过 `app/tools/registry.py` 暴露 5 个工具，供后续 Agent runtime 统一绑定。

**验收命令：**

```bash
uv run python -m pytest tests/integration/test_sales_tools.py -v
```

**完成标准：**

- 每个工具可独立调用。
- 工具不依赖 Agent 才能测试。
- 工具参数具备白名单或枚举校验。

---

### Phase 5：Agent Runtime 与多轮记忆

**目标：** 接入 LangChain 工具调用 Agent，支持 session 级上下文追问。

**加载参考：** `15`、`16`、`19`、`20`

**主要文件：**

- `app/agent/prompts.py`
- `app/agent/runtime.py`
- `app/agent/memory.py`
- `app/models/chat_memory.py`
- `app/repositories/chat_memory_repository.py`
- `app/schemas/agent.py`
- `tests/unit/test_agent_prompt.py`
- `tests/integration/test_agent_memory.py`

**任务：**

- [x] 设计 system prompt，明确 Agent 是销售数据分析助手。
- [x] 绑定 5 个工具到 LangChain Agent。
- [x] 实现 `session_id` 维度的消息历史。
- [x] 将用户消息、AI 回复和关键工具调用结果写入记忆。
- [x] 实现基础追问场景：第二轮不重复指定时间或区域时，能利用上一轮上下文。
- [x] Python 版使用 LangChain `create_agent` + `thread_id` 标识会话，默认从 MySQL `sa_chat_memory` 加载并保存最近 20 条会话消息快照；`checkpointer` 仅作为可注入扩展点保留，默认不启用内存记忆。

**验收命令：**

```bash
uv run pytest tests/unit/test_agent_prompt.py tests/integration/test_agent_memory.py -v
```

**完成标准：**

- Agent 能识别查询、统计、趋势、图表、预警类问题。
- 同一 session 保留上下文，不同 session 隔离。
- LLM 不可用时，测试可通过 fake model 或 mock tool-calling 验证业务链路。

---

### Phase 6：Agent API 与流式输出

**目标：** 对外提供同步聊天接口和流式聊天接口。

**加载参考：** `17`、`18`

**主要文件：**

- `app/api/v1/endpoints/agent.py`
- `app/agent/streaming.py`
- `tests/integration/test_agent_api.py`
- `tests/integration/test_agent_streaming.py`

**任务：**

- [x] 实现 `POST /api/v1/agent/chat`。
- [x] 实现 `POST /api/v1/agent/chat/stream`。
- [x] 请求体包含 `session_id`、`message`、可选用户上下文。
- [x] 响应体包含回答文本、工具调用摘要、引用的业务数据摘要。
- [x] 流式接口使用 SSE，保持错误事件格式统一。

**验收命令：**

```bash
uv run pytest tests/integration/test_agent_api.py tests/integration/test_agent_streaming.py -v
```

**完成标准：**

- 同步接口可返回完整分析。
- 流式接口可逐步输出文本事件。
- API 层不直接访问数据库，只调用 Agent runtime。

---

### Phase 7：认证、角色权限与数据隔离

**目标：** 让不同角色只能看到权限范围内的销售数据。

**加载参考：** `02`、`24`

**主要文件：**

- `app/models/user.py`
- `app/schemas/auth.py`
- `app/core/security.py`
- `app/core/context.py`
- `app/api/dependencies.py`
- `app/api/v1/endpoints/auth.py`
- `app/services/auth_service.py`
- `app/repositories/user_repository.py`
- `tests/integration/test_auth.py`
- `tests/integration/test_data_permissions.py`

**任务：**

- [ ] 定义角色：`SALES_REP`、`SALES_MANAGER`、`SALES_DIRECTOR`。
- [ ] 实现登录接口和 JWT 访问令牌。
- [ ] 在依赖注入中解析当前用户。
- [ ] 在 Service 查询条件中注入权限过滤：销售员只能看自己，主管只能看本大区，总监看全公司。
- [ ] 验证工具层调用同样受权限约束。

**验收命令：**

```bash
uv run pytest tests/integration/test_auth.py tests/integration/test_data_permissions.py -v
```

**完成标准：**

- 未登录访问受保护接口返回 401。
- 越权访问不会泄露数据。
- 权限过滤发生在 Service 层，Agent 和工具无法绕过。

---

### Phase 8：异常边界、缓存、日志、成本与安全

**目标：** 补齐生产化基础能力。

**加载参考：** `22`、`23`、`25`、`26`

**主要文件：**

- `app/core/errors.py`
- `app/core/logging.py`
- `app/services/cache_service.py`
- `app/services/token_usage_service.py`
- `app/schemas/common.py`
- `tests/unit/test_input_validation.py`
- `tests/integration/test_error_boundaries.py`
- `tests/integration/test_cache_service.py`

**任务：**

- [ ] 统一 API 错误返回结构。
- [ ] 统一工具错误返回结构。
- [ ] 增加参数白名单校验，特别是排序字段、时间范围、枚举条件。
- [ ] 避免 NL2SQL，所有查询走 SQLAlchemy 表达式。
- [ ] 增加请求日志、工具调用日志和 session 追踪 ID。
- [ ] 增加 token 使用记录接口或内部服务。
- [ ] 为高频统计查询增加可选 Redis 缓存。

**验收命令：**

```bash
uv run pytest tests/unit/test_input_validation.py tests/integration/test_error_boundaries.py tests/integration/test_cache_service.py -v
```

**完成标准：**

- 数据为空、参数非法、工具异常、模型异常都有稳定响应。
- 安全测试不能通过字符串参数影响 SQL 结构。
- Redis 不可用时系统能降级为无缓存运行。

---

### Phase 9：端到端场景验收

**目标：** 用参考文献中的业务场景验证完整链路。

**加载参考：** `17`、`19`、`20`、`21`

**主要文件：**

- `tests/e2e/test_simple_query_followup.py`
- `tests/e2e/test_multi_step_reasoning.py`
- `tests/e2e/test_chart_and_anomaly.py`
- `docs/specs/004-acceptance-scenarios.md`

**任务：**

- [ ] 验证简单查询与追问。
- [ ] 验证多步推理和多工具调用。
- [ ] 验证图表生成。
- [ ] 验证异常预警。
- [ ] 验证不同 session 之间记忆隔离。
- [ ] 验证不同角色看到的数据范围不同。

**验收命令：**

```bash
uv run pytest tests/e2e -v
```

**完成标准：**

- 核心场景能稳定通过。
- 每个场景都有明确断言，不只检查 HTTP 200。
- 无真实 LLM key 时，e2e 可使用 fake model 跑业务链路；有真实 key 时，可额外运行人工验收脚本。

---

## 五、依赖规划

第一阶段最小依赖：

- `fastapi`
- `uvicorn`
- `pydantic-settings`
- `pytest`
- `pytest-asyncio`
- `httpx`

数据库阶段依赖：

- `sqlalchemy`
- `aiosqlite`
- `alembic`

Agent 阶段依赖：

- `langchain`
- `langchain-openai`
- `langchain-core`

认证与安全阶段依赖：

- `python-jose`
- `passlib`
- `bcrypt`

缓存阶段依赖：

- `redis`

---

## 六、开发约束

- API 层不写业务查询。
- Tool 层不直接访问数据库。
- Service 层是权限过滤和业务规则的主边界。
- Repository 层只负责数据访问，不拼接不可信 SQL。
- Agent 只能通过工具访问销售数据。
- 测试优先覆盖 service 和 tools，再覆盖 Agent 与 API。
- 每个阶段完成后运行该阶段测试，再进入下一阶段。
- 每个阶段开始前先读取 `docs/reference/00_SUMMARY.md`，再按需打开原文。

---

## 七、里程碑

### M1：基础服务可运行

覆盖 Phase 1。

验收：FastAPI 应用启动，健康检查和基础测试通过。

### M2：销售数据可查询

覆盖 Phase 2、Phase 3。

验收：测试数据库可初始化，Service 能完成明细、汇总、排名、趋势查询。

### M3：工具层可独立工作

覆盖 Phase 4。

验收：5 个 LangChain tools 可独立调用并通过单元测试。

### M4：Agent 可完成核心问答

覆盖 Phase 5、Phase 6。

验收：同步聊天接口支持多轮追问，流式接口可输出事件。

### M5：具备生产基础防护

覆盖 Phase 7、Phase 8。

验收：权限隔离、安全校验、错误边界、日志和缓存策略可用。

### M6：参考场景全部通过

覆盖 Phase 9。

验收：简单追问、多步推理、图表、预警、权限隔离等 e2e 场景通过。

---

## 八、建议执行方式

先执行 Phase 0，产出项目蓝图和 API 契约。随后每个 Phase 单独生成更细的实施计划，实施计划应包含具体测试、具体文件修改和阶段验收命令。

推荐顺序：

1. `docs/specs/001-project-blueprint.md`
2. `docs/specs/002-architecture-and-module-boundaries.md`
3. `docs/specs/003-api-contract.md`
4. `docs/plans/002-phase-1-fastapi-foundation.md`
5. 按 Phase 1 到 Phase 9 逐步推进

这样可以避免一次性加载所有参考文献，也能保证每个阶段都有独立、可验证的成果。
