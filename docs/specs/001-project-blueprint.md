# 项目蓝图规格说明

## 1. 目标

本项目基于 `docs/reference/` 中的 LangChain4j 智能销售 Agent 参考文献，使用 Python、FastAPI、SQLAlchemy 和 LangChain 重建一个可运行、可测试、可持续增强的智能销售数据分析 Agent。

项目面向销售业务人员，支持用户用自然语言询问销售数据，并由 Agent 按需调用销售查询、统计排名、趋势分析、图表生成和异常预警工具，最终返回可读的业务分析结果。

## 2. 核心能力

本阶段规格冻结的核心能力如下：

- 销售订单明细查询：按时间、大区、销售员、产品等条件查询销售订单。
- 销售统计与排名：支持销售额汇总、销售员排名、大区排名、产品排名。
- 趋势分析：支持同比、环比、月度趋势等销售变化分析。
- 图表数据生成：生成面向 ECharts 消费的结构化图表 JSON。
- 异常预警：识别销售额异常、订单下降、人员表现异常等业务风险。
- 多轮对话：基于 `sessionId` 维护上下文，支持追问。
- 流式输出：通过 SSE 返回 token、tool、done、error 事件。
- 认证与权限：基于 JWT 识别当前用户，并按角色做数据隔离。

## 3. 能力边界

Agent 只回答与销售数据分析相关的问题。对超出能力范围的问题，应引导用户回到销售数据查询、统计、趋势、图表和异常预警场景。

Agent 不直接访问数据库，不生成或执行自然语言 SQL。所有业务数据访问必须通过 LangChain 工具进入 Service 层，再由 Repository 层使用 SQLAlchemy 表达式查询。

## 4. 不做事项

当前项目不包含：

- 前端页面开发。
- 真实企业生产数据库接入。
- 多租户 SaaS 管理后台。
- 复杂 BI 报表搭建器。
- 生产 Kubernetes、CI/CD、云监控部署。
- 让大模型自由生成 SQL 并执行。

## 5. 数据源与模型配置

开发阶段默认数据库为本地 MySQL。数据库表结构和测试数据由 `app/db/schema.sql`、`app/db/data.sql` 直接导入。

测试阶段允许使用内存 SQLite 验证 Repository、Service、Tool、API 等业务链路。SQLite 只服务自动化测试，不是运行时主数据源。

大模型通过 OpenAI 兼容协议接入阿里云百炼，配置从项目根目录 `.env` 读取：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_STREAMING_MODEL`

## 6. 用户与权限模型

系统当前定义三类角色：

- `SALES_REP`：普通销售员，只能查看本人负责的数据。
- `SALES_MANAGER`：销售主管，只能查看所属大区数据。
- `SALES_DIRECTOR`：销售总监，可以查看全公司数据。

权限过滤发生在 Service 层。API、Agent 和 Tool 层都不能绕过 Service 层直接读取销售数据。

## 7. 验证方式

规格落地后应通过以下方式验证：

- 项目能够通过 `uv run pytest -v` 执行现有自动化测试。
- `GET /health` 能返回应用状态。
- `POST /auth/login` 能签发 JWT。
- 携带 JWT 后，`POST /agent/chat` 能返回完整回答。
- 携带 JWT 后，`POST /agent/chat/stream` 能返回 SSE 事件，并在 `done` 事件中包含 `sessionId`。
- 不同角色查询同一类销售问题时，返回数据范围符合权限约束。
