# Phase 12 端到端场景验收规格

## 目标

使用参考项目中的核心业务场景验证当前 Python 重构项目的完整链路，覆盖 HTTP API、JWT 鉴权、依赖注入、Agent Runtime、会话记忆、LangChain 工具、Service 权限过滤、Repository 查询和测试数据库。

本阶段不依赖真实 LLM。测试中使用 fake Agent 只替代模型的自然语言决策过程，但 fake Agent 会调用真实工具，因此业务链路仍然完整。

## 验收范围

### 1. 简单查询与追问

用户先查询华东区销售员排行，再追问“第一名的订单明细”。系统必须：

- 第一轮返回排行结果，并指出 `Wang Fang`。
- 第二轮使用同一 `sessionId` 的历史上下文识别“第一名”。
- 第二轮调用 `query_sales_orders`，返回 `Wang Fang` 的订单 `ORD-002`。
- 第二轮不能混入其他销售员订单，例如 `ORD-001`。

对应测试：

```text
tests/e2e/test_simple_query_followup.py::test_simple_query_followup_uses_session_memory
```

### 2. 不同 Session 记忆隔离

一个 session 查询过排行后，另一个 session 直接追问“第一名”。系统必须：

- 不复用其他 session 的历史上下文。
- 返回缺少上下文的稳定回复。
- 不触发工具调用。

对应测试：

```text
tests/e2e/test_simple_query_followup.py::test_different_sessions_do_not_share_followup_memory
```

### 3. 不同角色数据权限

销售员和销售总监分别查询“1月所有订单”。系统必须：

- 销售员只能看到自己的订单。
- 销售总监可以看到全公司订单。
- 权限过滤发生在 Service 层，即使 Agent/Tool 请求全量数据，也不能越权。

对应测试：

```text
tests/e2e/test_simple_query_followup.py::test_e2e_role_permissions_filter_visible_orders
```

### 4. 多步推理与多工具调用

用户要求综合分析华东区 1 月销售额、环比和销售员排行。系统必须：

- 依次调用 `calculate_sales_summary`、`analyze_sales_trend`、`calculate_sales_summary`。
- 最终回答同时包含销售额、环比和排行信息。
- 工具调用摘要通过 API `toolCalls` 返回。

对应测试：

```text
tests/e2e/test_multi_step_reasoning.py::test_multi_step_reasoning_calls_summary_trend_and_ranking_tools
```

### 5. 图表生成

用户要求生成各大区销售占比图表。系统必须：

- 调用 `generate_sales_chart`。
- 返回 `CHART_JSON:{...}`。
- JSON 可被前端消费，且 `series[0].type` 为 `pie`。

对应测试：

```text
tests/e2e/test_chart_and_anomaly.py::test_chart_generation_returns_frontend_consumable_chart_json
```

### 6. 异常预警

用户要求检查销售异常预警。系统必须：

- 调用 `detect_sales_anomalies`。
- 返回稳定的业务预警文本。
- 在存在异常测试数据时，不返回“正常”结论。

对应测试：

```text
tests/e2e/test_chart_and_anomaly.py::test_anomaly_warning_returns_stable_business_alerts
```

## 测试策略

测试使用 FastAPI `ASGITransport` 直接调用应用，不启动外部 HTTP 服务。

测试数据库使用 SQLite 内存库和 `StaticPool`，保证同一次 e2e 测试内多个 HTTP 请求共享同一份数据。测试依赖覆盖 `get_db_session`，并模拟真实依赖的 commit/rollback 行为，确保会话记忆能跨请求读取。

Runtime 使用真实 `SalesAgentRuntime`，但通过 `agent_factory` 注入 fake Agent：

- fake Agent 根据用户消息选择工具。
- fake Agent 调用真实 LangChain tools。
- tools 继续调用真实 Service 和 Repository。
- 模型创建和摘要 middleware 在测试中替换为轻量对象，避免真实 LLM 调用。

## 验收命令

```bash
uv run python -m pytest tests/e2e -v
```

完整回归命令：

```bash
uv run python -m pytest -v
```
