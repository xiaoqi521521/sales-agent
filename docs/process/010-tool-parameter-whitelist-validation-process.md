# 工具参数白名单校验编写过程

## 1. 任务范围

本阶段对应计划书 Phase 11 的“SQL 注入防护与参数白名单”，本次只完成工具参数白名单校验。

实际完成内容：

- 使用 Pydantic 作为 LangChain 工具参数的唯一校验入口。
- 对日期格式、日期范围、大区名称、图表类型、图表维度、`limit`、`top_n`、`months` 做约束。
- 删除工具函数中的数值静默修正逻辑，非法参数不再被自动压缩到合法范围。
- 在 Agent/LangChain 调用边界捕获 Pydantic 参数异常，并转换成可读错误。
- 同步测试中的大区数据口径，使用参考数据中的 `华东区`、`华南区`、`华北区`、`西南区`。

未纳入本阶段：

- 不新增数据库表。
- 不新增依赖。
- 不实现 Redis 缓存。
- 不引入 NL2SQL。
- 不新增模型生成 SQL 或执行任意 SQL 的能力。
- 不重写 Repository 查询层。
- 不对 `customer_name`、`title`、`rep_name` 做白名单校验。

## 2. 参考资料

主要参考：

- `docs/reference/00_SUMMARY.md`
- `docs/reference/26_SQL注入防护.md`
- `docs/specs/project/003-tool-parameter-whitelist-validation.md`

关键设计结论：

- Repository 层已经使用 SQLAlchemy 表达式和参数绑定，不把字符串参数拼接进 SQL。
- Phase 11 的新增重点是工具层参数白名单，而不是重写查询层。
- 参数非法时应显式失败，不做静默转换。
- 参数异常发生在工具函数执行前，不在工具函数内部捕获。

## 3. 测试先行

先新增失败测试，再实现。

新增测试：

- `tests/unit/test_input_validation.py`
  - 验证 SQL 注入形态的大区名称被 Pydantic 拦截。
  - 验证未知大区名称被 Pydantic 拦截。
  - 验证日期格式错误和日期顺序错误被 Pydantic 拦截。
  - 验证 `limit`、`top_n`、`months` 越界被 Pydantic 拦截。
  - 验证合法白名单参数可通过，并会对大区名称做 `strip()`。
- `tests/integration/test_tool_parameter_validation.py`
  - 验证同步 Agent runtime 能把 Pydantic `ValidationError` 转换为 `TOOL_INVALID_ARGUMENT` 可读文本。
  - 验证流式 Agent runtime 能把 Pydantic `ValidationError` 转换为 SSE `error` 事件。

红灯验证：

```text
6 failed
```

失败原因包括：

- `region_name` 没有白名单校验。
- 日期格式和日期顺序没有在 schema 层校验。
- 数值参数仍可越界进入工具。
- `region_name` 不会 `strip()`。
- Agent runtime 遇到参数校验异常时仍继续抛出异常。

## 4. Pydantic 参数校验入口

主要修改文件：`app/tools/schemas.py`。

新增白名单和通用校验逻辑：

- `ALLOWED_REGION_NAMES = {"华东区", "华南区", "华北区", "西南区"}`。
- 日期必须符合 `yyyy-MM-dd`。
- 同一日期范围内，开始日期不能晚于结束日期。
- `region_name` 为 `None` 或空字符串时表示不限制；非空时必须属于白名单。

各 schema 的约束：

- `SalesQueryInput`
  - `start_date`、`end_date` 必填并校验格式和顺序。
  - `limit` 使用 `Field(ge=1, le=50)`。
- `SalesSummaryInput`
  - `summary_type` 保留 `Literal` 枚举。
  - `top_n` 使用 `Field(ge=-20, le=20)`，并禁止 0。
- `SalesTrendInput`
  - `trend_type` 保留 `Literal` 枚举。
  - `current_start/current_end`、`previous_start/previous_end` 校验格式和顺序。
  - `months` 使用 `Field(ge=1, le=24)`。
- `SalesChartInput`
  - `chart_type`、`dimension` 保留 `Literal` 枚举。
  - `start_date/end_date` 校验格式和顺序。
  - `months` 使用 `Field(ge=1, le=24)`。

## 5. 工具层改造

涉及文件：

- `app/tools/sales_query_tool.py`
- `app/tools/sales_summary_tool.py`
- `app/tools/sales_trend_tool.py`
- `app/tools/chart_generator_tool.py`
- `app/tools/formatting.py`

改造点：

- 删除工具中的 `clamp(...)` 调用。
- 删除 `app/tools/formatting.py` 中未再使用的 `clamp` helper。
- 工具函数继续保留业务边界处理，例如空数据、实体不存在、权限不足、服务异常。
- 工具函数内部不捕获 Pydantic `ValidationError`。

改造后的数值行为：

```text
limit=1000
-> Pydantic ValidationError
-> query_sales_orders 不执行
```

```text
top_n=0
-> Pydantic ValidationError
-> calculate_sales_summary 不执行
```

```text
months=100
-> Pydantic ValidationError
-> analyze_sales_trend / generate_sales_chart 不执行
```

## 6. Agent 边界异常转换

主要修改文件：`app/agent/runtime.py`。

同步接口链路：

```text
SalesAgentRuntime.chat_with_trace(...)
-> self.agent.ainvoke(payload, config=config)
-> LangChain 调用工具 args_schema
-> Pydantic 抛 ValidationError
-> runtime 捕获 ValidationError
-> 返回 AgentRunResult(reply="TOOL_INVALID_ARGUMENT\n工具参数不合法...")
```

流式接口链路：

```text
SalesAgentRuntime.stream_chat(...)
-> self.agent.ainvoke(...) 或 self.agent.astream(...)
-> LangChain 调用工具 args_schema
-> Pydantic 抛 ValidationError
-> runtime 捕获 ValidationError
-> yield AgentStreamEvent(event="error", data={"message": "TOOL_INVALID_ARGUMENT\n..."})
```

这里不在工具函数内部捕获 Pydantic 异常，原因是参数校验发生在工具函数执行前。runtime 是更合适的 Agent/LangChain 调用边界。

## 7. 工具执行链路

合法参数链路：

```text
用户问题
-> LLM 选择工具并生成参数
-> LangChain 根据 args_schema 调用 Pydantic 校验
-> 校验通过
-> 工具函数开始执行
-> tool_call_started(...)
-> Service
-> Repository 使用 SQLAlchemy 表达式和参数绑定查询
-> tool_call_finished(...)
-> 返回工具结果
```

非法参数链路：

```text
用户问题
-> LLM 生成非法工具参数
-> LangChain 根据 args_schema 调用 Pydantic 校验
-> Pydantic 抛 ValidationError
-> 工具函数不执行
-> 不打印 tool_call_started / tool_call_completed
-> Agent runtime 捕获并转换为可读错误
```

## 8. 测试数据同步

本阶段把受影响测试中的工具参数大区名称从旧英文示例同步为参考数据口径：

```text
East -> 华东区
North -> 华北区
```

说明：

- 这只影响工具参数白名单入口。
- Service/Repository 的权限过滤逻辑未改变。
- `customer_name`、`rep_name` 等动态业务实体仍不做白名单校验。

## 9. 验证

新增测试验证命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_input_validation.py tests/integration/test_tool_parameter_validation.py -v
```

结果：

```text
7 passed
```

受影响范围回归命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_sales_tools.py tests/integration/test_data_permissions.py tests/integration/test_agent_api.py tests/integration/test_agent_streaming.py tests/unit/test_input_validation.py tests/integration/test_tool_parameter_validation.py -v
```

结果：

```text
21 passed
```
