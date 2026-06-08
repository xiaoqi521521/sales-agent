# 日志追踪与 Token 成本控制 Spec

## 背景与目标

AI Agent 上线后需要先回答两个最直接的问题：

- Agent 做了什么：是否能在控制台看到请求、Agent 执行和工具调用过程。
- 本次调用大概花了多少：是否能在控制台看到 input token、output token、total token 和估算费用。

本阶段只做轻量级日志追踪和 token 成本打印，不做持久化、不做报表、不新增数据库表。

参考文献：

- `docs/reference/00_SUMMARY.md`
- `docs/reference/23_日志追踪与token成本控制.md`

参考文献中的核心思路：

- 使用工具调用前后回调记录工具名称、参数、结果长度。
- 使用模型监听器获取 token usage。
- 根据 input/output token 单价估算费用。
- 通过控制记忆窗口、缓存高频问题、截断工具结果、精简 system prompt 降低成本。

Python 版对应：

- 工具调用日志打印到控制台。
- Token usage 优先从 LangChain usage metadata 中读取。
- Token 单价通过 `.env` 配置，默认使用当前 deepseek-v4-flash 计费：输入 1 元/百万 tokens，输入缓存命中 0.2 元/百万 tokens，输出 2 元/百万 tokens。
- 费用估算结果打印到控制台。

官方用法核实：

- LangChain 官方文档推荐通过 `UsageMetadataCallbackHandler`、`get_usage_metadata_callback()` 或 `AIMessage.usage_metadata` 获取 token 使用量。
- FastAPI 官方文档推荐使用 HTTP middleware 处理每个请求、记录耗时并修改响应头，因此 traceId 和请求日志放在 middleware 中是合适的。

## In Scope

- 增加控制台日志配置。
- 为每次 HTTP 请求生成或复用 `traceId`，并写入响应头 `X-Trace-Id`。
- 控制台打印 HTTP 请求开始、完成、异常、耗时。
- 控制台打印 Agent 开始、完成、异常、耗时、sessionId。
- 控制台打印工具调用开始、完成、结果长度、耗时。
- 控制台打印工具错误前缀，例如 `TOOL_EMPTY_DATA`、`TOOL_EXECUTION_ERROR`。
- 控制台打印 token 用量和估算费用。
- 增加 token 单价配置。
- 增加测试验证 traceId、日志输出、费用计算。
- 实现完成后，同步编写 `docs/process/009-logging-and-token-cost-control-process.md`。

## Out of Scope

- 不新增数据库表。
- 不持久化 token 用量。
- 不新增 Repository、Model 或数据库迁移。
- 不提供成本查询 API。
- 不做成本报表、图表或管理后台。
- 不接入 LangSmith、OpenTelemetry、Prometheus 等外部可观测系统。
- 不实现 Redis 缓存。
- 不实现用户级、角色级、日/月级预算拦截。
- 不修改成功响应 JSON body。

---

## 日志设计

### 日志输出位置

日志打印到控制台。

开发阶段通过 `uv run python app/main.py` 或 `uv run uvicorn app.main:app --reload` 启动后，可以直接在控制台观察日志。

### 日志格式

采用单行结构化文本，便于阅读和 grep。

示例：

```text
INFO event=http_request_completed traceId=trace-test-001 method=POST path=/agent/chat statusCode=200 durationMs=123
INFO event=agent_run_completed traceId=trace-test-001 sessionId=scenario-001 model=deepseek-v4-flash durationMs=980 toolCalls=1
INFO event=tool_call_completed traceId=trace-test-001 toolName=calculate_sales_summary durationMs=26 resultLength=342
INFO event=token_usage traceId=trace-test-001 sessionId=scenario-001 model=deepseek-v4-flash inputTokens=800 outputTokens=300 totalTokens=1100 estimatedCost=0.000000 currency=CNY
```

不要求输出严格 JSON。

### 日志事件

| event | 说明 |
| --- | --- |
| `http_request_started` | HTTP 请求进入应用 |
| `http_request_completed` | HTTP 请求正常结束 |
| `http_request_failed` | HTTP 请求异常结束 |
| `agent_run_started` | Agent 开始处理 |
| `agent_run_completed` | Agent 正常完成 |
| `agent_run_failed` | Agent 异常 |
| `tool_call_started` | 工具调用开始 |
| `tool_call_completed` | 工具调用完成 |
| `tool_call_failed` | 工具返回错误前缀或执行异常 |
| `token_usage` | token 用量和费用估算 |
| `token_usage_unavailable` | 模型未返回 token usage |
| `token_cost_threshold_exceeded` | token 或费用超过告警阈值 |

### 敏感信息约束

日志不得打印：

- `Authorization` 请求头。
- JWT 原文。
- API key。
- 数据库连接串。
- 完整用户原始问题。

用户问题最多打印长度：

```text
messageLength=18
```

---

## TraceId 设计

### 生成规则

每个 HTTP 请求都带一个 `traceId`。

规则：

1. 如果请求头包含 `X-Trace-Id`，复用该值。
2. 如果请求头没有 `X-Trace-Id`，服务端生成 UUID。

### 响应规则

所有 HTTP 响应头都返回：

```http
X-Trace-Id: <traceId>
```

SSE 流式接口也返回该响应头，但不要求每个 SSE event 都携带 traceId。

---

## 工具调用日志

参考 LangChain4j 的 `beforeToolExecution` / `afterToolExecution` 思路。

工具调用开始：

```text
INFO event=tool_call_started traceId=trace-test-001 toolName=query_sales_orders argumentsLength=128
```

工具调用完成：

```text
INFO event=tool_call_completed traceId=trace-test-001 toolName=query_sales_orders durationMs=18 resultLength=512
```

工具返回错误前缀：

```text
WARN event=tool_call_failed traceId=trace-test-001 toolName=query_sales_orders durationMs=18 errorCode=TOOL_EMPTY_DATA resultLength=96
```

工具参数不打印完整内容，只打印参数字符串长度或字段数量。

---

## Token 用量与费用打印

### Token 来源

优先级：

1. 使用 LangChain `get_usage_metadata_callback()` 或 `UsageMetadataCallbackHandler` 获取模型调用 usage。
2. 如果最终 AIMessage 中存在 `usage_metadata`，作为补充来源。
3. 如果模型或流式模式没有返回 usage，打印 `token_usage_unavailable`，不影响用户请求。

### 配置项

新增 `.env` 配置：

```env
TOKEN_INPUT_PRICE_PER_1M=1
TOKEN_CACHED_INPUT_PRICE_PER_1M=0.2
TOKEN_OUTPUT_PRICE_PER_1M=2
TOKEN_COST_CURRENCY=CNY
TOKEN_WARN_TOTAL_THRESHOLD=0
TOKEN_WARN_COST_THRESHOLD=0
```

说明：

- `TOKEN_INPUT_PRICE_PER_1M`：每 100 万 input tokens 的价格。
- `TOKEN_CACHED_INPUT_PRICE_PER_1M`：每 100 万缓存命中 input tokens 的价格。
- `TOKEN_OUTPUT_PRICE_PER_1M`：每 100 万 output tokens 的价格。
- `TOKEN_COST_CURRENCY`：币种，默认 `CNY`。
- `TOKEN_WARN_TOTAL_THRESHOLD`：单次 total tokens 告警阈值，0 表示关闭。
- `TOKEN_WARN_COST_THRESHOLD`：单次估算费用告警阈值，0 表示关闭。

### 费用公式

```text
estimated_cost =
  normal_input_tokens / 1_000_000 * TOKEN_INPUT_PRICE_PER_1M
  + cached_input_tokens / 1_000_000 * TOKEN_CACHED_INPUT_PRICE_PER_1M
  + output_tokens / 1_000_000 * TOKEN_OUTPUT_PRICE_PER_1M
```

其中：

```text
cached_input_tokens = usage.input_token_details.cache_read 或 0
normal_input_tokens = max(input_tokens - cached_input_tokens, 0)
```

示例：

```text
INFO event=token_usage traceId=trace-test-001 sessionId=scenario-001 model=deepseek-v4-flash inputTokens=1000000 cachedInputTokens=200000 outputTokens=500000 totalTokens=1500000 estimatedCost=1.840000 currency=CNY
```

计算过程：

```text
普通输入 800000 tokens * 1 / 1000000 = 0.8
缓存输入 200000 tokens * 0.2 / 1000000 = 0.04
输出 500000 tokens * 2 / 1000000 = 1.0
合计 = 1.84 元
```

如果模型 usage metadata 没有提供缓存命中详情，则 `cachedInputTokens=0`，全部 input tokens 按普通输入价格估算。

### 阈值告警

如果超过配置阈值，只打印 warning，不阻断请求。

示例：

```text
WARN event=token_cost_threshold_exceeded traceId=trace-test-001 totalTokens=1500 estimatedCost=0.100000
```

---

## 成本控制策略

本阶段不做强制成本拦截，只提供观察和告警。

参考文献中的降本策略在本项目中的处理：

- 控制记忆窗口大小：保留当前 `ChatMemoryService(max_messages=20)`，本阶段不修改。
- 缓存高频问题：留到 Redis 缓存阶段。
- 工具结果截断：现有查询工具已有 `limit` 和上限控制，本阶段只打印 `resultLength`，为后续优化提供依据。
- 精简 system prompt：本阶段不改 prompt，避免影响 Agent 行为。

---

## 模块设计

### `app/core/logging.py`

职责：

- 配置控制台日志格式。
- 提供 `get_logger(name)`。
- 提供统一的 key-value 日志格式化 helper。

### `app/core/request_context.py`

职责：

- 使用 `contextvars` 保存当前请求 `traceId`。
- 提供 `get_trace_id()`、`set_trace_id()`、`reset_trace_id()`。

### `app/api/middleware.py`

职责：

- 读取或生成 `X-Trace-Id`。
- 写入请求上下文。
- 打印 HTTP 请求开始、完成、失败日志。
- 在响应头写入 `X-Trace-Id`。

### `app/core/token_usage.py`

职责：

- 聚合 usage metadata。
- 根据配置计算估算费用。
- 打印 token usage 日志。
- 超过阈值时打印 warning 日志。

不负责数据库写入。

说明：

- 本模块不放在 `app/services/`，因为它不是销售业务服务，而是基础设施/可观测性 helper。
- Controller 不直接调用它。同步和流式 Agent 的 token usage 都发生在 `app/agent/runtime.py` 的模型调用边界，因此由 Agent runtime 调用该 helper 更合适。

### `app/agent/runtime.py`

职责：

- 在同步 `chat_with_trace` 中采集 token usage 并打印费用。
- 在流式 `stream_chat` 中尽量采集 token usage；拿不到 usage 时打印 `token_usage_unavailable`。
- 打印 Agent 开始、完成、失败日志。

### `app/tools` 或工具包装层

职责：

- 打印工具开始和完成日志。
- 记录工具结果长度。
- 识别 `TOOL_*` / `NO_PERMISSION_*` 前缀并打印 `tool_call_failed`。

优先选择统一包装方式；如果 LangChain tool 对象包装不稳定，则在各工具内部记录。

---

## 接口行为

### HTTP 响应头

所有接口返回：

```http
X-Trace-Id: <traceId>
```

### `POST /agent/chat`

成功响应 body 保持不变。

新增控制台日志：

- HTTP 请求日志。
- Agent 运行日志。
- 工具调用日志。
- Token 用量和费用估算日志。

### `POST /agent/chat/stream`

SSE event 结构保持不变。

新增控制台日志：

- HTTP 请求日志。
- Agent 流式运行日志。
- 工具调用日志。
- 若可获取 usage，则打印 token usage；否则打印 `token_usage_unavailable`。

---

## 验收标准

### 场景一：HTTP 响应返回 traceId

GIVEN 请求头没有 `X-Trace-Id`  
WHEN 调用 `GET /health`  
THEN 响应头包含服务端生成的 `X-Trace-Id`。

### 场景二：复用客户端传入 traceId

GIVEN 请求头包含 `X-Trace-Id: trace-test-001`  
WHEN 调用 `POST /agent/chat`  
THEN 响应头 `X-Trace-Id` 等于 `trace-test-001`。

### 场景三：HTTP 请求打印控制台日志

GIVEN 调用 `GET /health`  
WHEN 请求完成  
THEN 控制台日志中包含 `event=http_request_completed`、`traceId`、`method`、`path`、`statusCode`、`durationMs`。

### 场景四：工具调用打印开始和完成日志

GIVEN 调用任意工具  
WHEN 工具执行完成  
THEN 控制台日志中包含 `tool_call_started` 和 `tool_call_completed`，并包含 `toolName`、`durationMs`、`resultLength`。

### 场景五：工具错误前缀打印失败日志

GIVEN 工具返回 `TOOL_EMPTY_DATA`  
WHEN 工具执行完成  
THEN 控制台日志中包含 `event=tool_call_failed` 和 `errorCode=TOOL_EMPTY_DATA`。

### 场景六：token 成本按配置计算

GIVEN `TOKEN_INPUT_PRICE_PER_1M=1`，`TOKEN_CACHED_INPUT_PRICE_PER_1M=0.2`，`TOKEN_OUTPUT_PRICE_PER_1M=2`  
WHEN input_tokens=1000000，cached_input_tokens=200000，output_tokens=500000  
THEN estimated_cost 等于 `1.840000`。

### 场景七：有 usage metadata 时打印 token usage

GIVEN fake usage metadata 包含 input=1000、output=500、total=1500  
WHEN Agent 执行完成  
THEN 控制台日志中包含 `event=token_usage`、`inputTokens=1000`、`outputTokens=500`、`totalTokens=1500`。

### 场景八：没有 usage metadata 时不阻断请求

GIVEN 模型返回没有 usage metadata  
WHEN Agent 执行完成  
THEN 请求仍成功，控制台日志包含 `event=token_usage_unavailable`。

### 场景九：超过阈值打印 warning

GIVEN `TOKEN_WARN_TOTAL_THRESHOLD=100`  
WHEN total_tokens=150  
THEN 控制台日志包含 `event=token_cost_threshold_exceeded`，请求不被阻断。

### 场景十：日志不泄露敏感信息

GIVEN 请求头包含 `Authorization`  
WHEN 打印请求日志  
THEN 日志中不包含 JWT 原文、API key 或数据库连接串。

---

## 预期修改文件

- `app/core/config.py`
- `app/core/logging.py`
- `app/core/request_context.py`
- `app/api/middleware.py`
- `app/main.py`
- `app/agent/runtime.py`
- `app/core/token_usage.py`
- `tests/unit/test_token_usage.py`
- `tests/integration/test_logging_and_trace.py`
- `tests/integration/test_tool_logging.py`
- `tests/integration/test_agent_token_logging.py`
- `docs/process/009-logging-and-token-cost-control-process.md`

## 验收命令

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/unit/test_token_usage.py tests/integration/test_logging_and_trace.py tests/integration/test_tool_logging.py tests/integration/test_agent_token_logging.py -v
```

完整回归：

```powershell
$env:PYTHONPATH='.'; uv run pytest -v
```

## 技术约束

- 不新增数据库表。
- 不做 token 使用持久化。
- 不改变成功响应 JSON body。
- 不在代码中硬编码具体模型价格。
- 不记录完整用户原始问题。
- 不记录 `Authorization`、JWT、API key、数据库连接串。
- traceId 只用于追踪，不用于认证。
- token usage 获取失败不能阻断用户请求。
- 如需新依赖，必须先说明用途和必要性；优先使用 Python 标准库和现有 LangChain 能力。
