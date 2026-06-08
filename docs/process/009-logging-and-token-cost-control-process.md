# 日志追踪与 Token 成本控制编写过程

## 1. 任务范围

本阶段对应 Phase 8 的“日志追踪与 token 成本控制”。

实际完成内容：

- 控制台打印 HTTP 请求日志。
- 为每次请求生成或复用 `traceId`，并写入响应头 `X-Trace-Id`。
- 控制台打印 Agent 开始、完成、异常日志。
- 控制台打印工具调用开始、完成、错误前缀和结果长度。
- 控制台打印 token 用量、缓存命中输入 token、估算费用。
- 增加 token 单价配置，按每百万 tokens 计算费用。

未纳入本阶段：

- 不新增数据库表。
- 不持久化 token 用量。
- 不新增成本查询 API。
- 不接入 LangSmith、OpenTelemetry、Prometheus 等外部观测系统。
- 不实现 Redis 缓存。
- 不做用户预算拦截。

## 2. 参考资料

主要参考：

- `docs/reference/00_SUMMARY.md`
- `docs/reference/23_日志追踪与token成本控制.md`
- `docs/specs/project/002-logging-and-token-cost-control.md`

参考文献 23 的关键点：

- 工具调用前后记录工具名称、参数和结果长度。
- 模型响应后统计 input/output token。
- 根据 token 单价估算费用。
- 通过控制记忆窗口、缓存高频问题、截断工具结果、精简 system prompt 降低成本。

通过 Context7 核实的官方用法：

- LangChain Python 当前推荐使用 `UsageMetadataCallbackHandler` 或 `get_usage_metadata_callback()` 聚合 token usage。
- LangChain 的 `AIMessage.usage_metadata` 也可以作为 token usage 来源。
- FastAPI 推荐通过 HTTP middleware 处理每个请求、记录耗时并修改响应头。

## 3. 测试先行

先补测试，再实现。

新增测试：

- `tests/unit/test_token_usage.py`
  - 验证按每百万 tokens 价格计算费用。
  - 验证从 usage metadata 中提取缓存命中输入 token。
- `tests/integration/test_logging_and_trace.py`
  - 验证响应头包含 `X-Trace-Id`。
  - 验证客户端传入的 traceId 会被复用。
  - 验证 HTTP 请求完成日志包含 method、path、statusCode、durationMs。
  - 验证日志不输出 Authorization 原文。
- `tests/integration/test_tool_logging.py`
  - 验证工具调用会打印开始日志。
  - 验证工具返回 `TOOL_EMPTY_DATA` 时打印失败日志和错误前缀。
- `tests/integration/test_agent_token_logging.py`
  - 验证 Agent runtime 能从 AIMessage usage metadata 打印 token usage 日志。

红灯验证：

- `app.core.token_usage` 尚不存在时，token usage 单元测试导入失败。
- Agent runtime 未接入 token usage 时，集成测试无法找到 `event=token_usage`。

## 4. 控制台日志基础设施

新增 `app/core/logging.py`：

- 使用 Python 标准库 `logging`。
- 控制台输出格式为 `LEVEL key=value key=value`。
- 提供 `format_kv(...)` 统一构造日志文本。

新增 `app/core/request_context.py`：

- 使用 `contextvars` 保存当前请求的 `traceId`。
- 提供 `get_trace_id()`、`set_trace_id()`、`reset_trace_id()`。

新增 `app/api/middleware.py`：

- 读取请求头 `X-Trace-Id`，没有则生成 UUID。
- 将 traceId 写入上下文。
- 打印 `http_request_started`、`http_request_completed`、`http_request_failed`。
- 在响应头写入 `X-Trace-Id`。
- 每个请求开始前先打印 80 个 `=` 作为控制台分隔符，方便区分不同请求的日志块。

在 `app/main.py` 中注册日志配置和 trace middleware。

## 5. Token 成本计算

新增 `app/core/token_usage.py`。

没有放在 `app/services/` 的原因：

- token 用量统计不是销售业务服务。
- Controller 不直接调用它。
- token usage 出现在 Agent 调用模型的边界，因此由 `app/agent/runtime.py` 调用更合适。

新增配置项位于 `app/core/config.py`：

```env
TOKEN_INPUT_PRICE_PER_1M=1
TOKEN_CACHED_INPUT_PRICE_PER_1M=0.2
TOKEN_OUTPUT_PRICE_PER_1M=2
TOKEN_COST_CURRENCY=CNY
TOKEN_WARN_TOTAL_THRESHOLD=0
TOKEN_WARN_COST_THRESHOLD=0
```

费用公式：

```text
normal_input_tokens / 1_000_000 * TOKEN_INPUT_PRICE_PER_1M
+ cached_input_tokens / 1_000_000 * TOKEN_CACHED_INPUT_PRICE_PER_1M
+ output_tokens / 1_000_000 * TOKEN_OUTPUT_PRICE_PER_1M
```

示例：

```text
input_tokens=1000000
cached_input_tokens=200000
output_tokens=500000
estimated_cost=1.840000
```

## 6. Agent Runtime 接入

在 `app/agent/runtime.py` 中完成：

- `chat_with_trace` 开始时打印 `agent_run_started`。
- 调用 Agent 时使用 LangChain 官方 `get_usage_metadata_callback()` 采集 token usage。
- 如果 callback 未获得 usage，则回退读取最终 AIMessage 的 `usage_metadata`。
- 正常结束时打印 `token_usage` 和 `agent_run_completed`。
- 异常时打印 `agent_run_failed`。

流式接口目前在无法稳定取得 usage 时打印 `token_usage_unavailable`，不影响 SSE 正常返回。

## 7. 工具调用日志

新增 `app/tools/logging.py`：

- `tool_call_started(...)`
- `tool_call_finished(...)`

接入 5 个工具：

- `query_sales_orders`
- `calculate_sales_summary`
- `analyze_sales_trend`
- `generate_sales_chart`
- `detect_sales_anomalies`

工具日志记录：

- 工具名称。
- 参数字符串长度。
- 执行耗时。
- 返回结果长度。
- `TOOL_*` 或 `NO_PERMISSION_*` 错误前缀。

工具参数不打印完整内容，避免泄露用户输入或业务敏感信息。

## 8. 模块内部执行链路

本阶段的日志追踪和 token 成本控制不是由 Controller 直接完成，而是分布在应用启动、HTTP middleware、Agent runtime、工具层和 token usage helper 中。整体链路如下。

### 8.1 应用启动链路

```text
app/main.py
-> create_app()
-> configure_logging()
-> register_trace_middleware(app)
-> include_router(api_router)
-> register_exception_handlers(app)
```

启动时先执行 `configure_logging()`，把 Python root logger 配置为控制台输出和 `INFO` 级别。随后注册 trace middleware，让每个 HTTP 请求都会先经过 `app/api/middleware.py`。因此请求日志、traceId、控制台分隔符都不需要在每个 API 接口里重复编写。

### 8.2 HTTP 请求日志链路

```text
客户端请求
-> trace_middleware(request, call_next)
-> 读取 X-Trace-Id；没有则生成 UUID
-> set_trace_id(trace_id)
-> 打印 80 个 "=" 分隔符
-> 打印 event=http_request_started
-> call_next(request)
-> API endpoint / Agent / Service / Tool
-> response.headers["X-Trace-Id"] = trace_id
-> 打印 event=http_request_completed
-> reset_trace_id(...)
-> 返回响应
```

如果中间发生异常，链路变为：

```text
call_next(request)
-> 抛出异常
-> 打印 event=http_request_failed
-> reset_trace_id(...)
-> 继续抛出异常
-> FastAPI 全局异常处理器返回统一错误响应
```

`traceId` 使用 `contextvars` 保存。这样 API、Agent、Tool、Token usage helper 只要调用 `format_kv(...)`，日志里就会自动带上当前请求的 `traceId`，不用层层传递 traceId 参数。

### 8.3 同步 Agent 调用链路

同步接口 `/agent/chat` 的主要链路如下：

```text
app/api/v1/endpoints/agent.py
-> get_sales_agent_runtime()
-> SalesAgentRuntime.chat_with_trace(session_id, message)
-> 校验 session_id 和 message
-> 打印 event=agent_run_started
-> _build_agent_input(...)
   -> ChatMemoryService.get_context_messages(...)
   -> 拼接历史消息和当前用户消息
   -> 生成 LangGraph thread_id 配置
-> get_usage_metadata_callback()
-> self.agent.ainvoke(payload, config=config)
   -> 模型判断是否需要工具
   -> LangChain 执行工具
   -> 模型根据工具结果生成最终回答
-> _extract_answer(result)
-> _extract_tool_messages(result)
-> summarize_usage_metadata(callback.usage_metadata)
-> log_token_usage(...)
-> ChatMemoryService.append_turn(...)
-> 打印 event=agent_run_completed
-> 返回 AgentRunResult
```

这里 token 用量统计放在 `app/agent/runtime.py` 调用，是因为 token usage 出现在模型调用边界。Controller 不知道模型实际调用了几次，也不直接接触 LangChain usage metadata，因此不适合在 Controller 层统计。

### 8.4 流式 Agent 调用链路

流式接口 `/agent/chat/stream` 的主要链路如下：

```text
app/api/v1/endpoints/agent.py
-> SalesAgentRuntime.stream_chat(session_id, message)
-> 校验 session_id 和 message
-> _build_agent_input(...)
-> self.agent.astream(..., stream_mode=["messages", "updates"])
   -> messages: 提取 token 文本，yield event=token
   -> updates/tools: 提取工具结果，yield event=tool
   -> updates/model: 记录模型完整回答作为兜底
-> 拼接完整 answer
-> log_token_usage(...)
-> ChatMemoryService.append_turn(...)
-> yield event=done
```

当前流式模式下，如果不能稳定从 LangChain stream 中取得 usage metadata，则打印：

```text
event=token_usage_unavailable
```

这不会阻断 SSE 返回。同步接口优先打印真实 `token_usage`，流式接口目前以不中断用户体验为主。

### 8.5 工具调用日志链路

每个销售工具内部都遵循同一模式：

```text
LangChain 调用工具
-> tool_call_started(tool_name, arguments)
   -> 打印 event=tool_call_started
   -> 返回 started_at
-> 执行业务查询
   -> service
   -> repository
   -> database
-> 得到工具返回文本
-> tool_call_finished(tool_name, started_at, result)
   -> 计算 durationMs
   -> 如果 result 以 TOOL_* 或 NO_PERMISSION_* 开头，打印 event=tool_call_failed
   -> 否则打印 event=tool_call_completed
   -> 返回原始 result 给 LangChain
```

工具日志只打印参数字符串长度和结果长度，不打印完整参数和完整结果，避免泄露用户问题、JWT、数据库连接串或业务敏感数据。

需要注意：模型一次回复中可能返回多个 tool calls。LangChain 在执行这些工具时可能出现多个 `tool_call_started` 连续打印，然后再陆续出现 `tool_call_completed`。这代表工具调用存在批量或并发执行迹象，不代表日志顺序错误。

### 8.6 Token 用量和费用计算链路

```text
LangChain usage metadata
-> summarize_usage_metadata(metadata)
   -> 读取 input_tokens
   -> 读取 output_tokens
   -> 读取 total_tokens；缺失时使用 input_tokens + output_tokens
   -> 读取 input_token_details.cache_read 作为 cached_input_tokens
-> calculate_estimated_cost(usage, settings)
   -> 普通输入 token = input_tokens - cached_input_tokens
   -> 缓存命中输入 token = cached_input_tokens
   -> 输出 token = output_tokens
   -> 按每百万 tokens 单价估算费用
-> log_token_usage(...)
   -> 打印 event=token_usage
   -> 如超过阈值，打印 event=token_cost_threshold_exceeded
```

费用计算不直接使用 `total_tokens`，而是分别使用普通输入、缓存输入和输出 token。这样可以正确应用不同单价，避免把缓存命中输入 token 按普通输入价格重复计费。

### 8.7 一次同步请求的日志顺序示例

```text
INFO ================================================================================
INFO event=http_request_started ...
INFO event=agent_run_started ...
INFO HTTP Request: POST https://dashscope.aliyuncs.com/...
INFO event=tool_call_started ...
INFO event=tool_call_completed ...
INFO HTTP Request: POST https://dashscope.aliyuncs.com/...
INFO event=token_usage ...
INFO event=agent_run_completed ...
INFO event=http_request_completed ...
INFO:     127.0.0.1:xxxx - "POST /agent/chat HTTP/1.1" 200 OK
```

其中 `HTTP Request: POST https://dashscope...` 通常来自底层 `httpx` 或相关模型客户端库，表示向阿里云百炼兼容接口发起了一次模型 HTTP 请求。最后一行 `INFO: 127.0.0.1...` 是 Uvicorn access log，不是本项目业务日志。

## 9. 验证

目标测试命令：

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/unit/test_token_usage.py tests/integration/test_logging_and_trace.py tests/integration/test_tool_logging.py tests/integration/test_agent_token_logging.py -v
```

目标测试结果：

```text
7 passed
```

完整回归命令：

```powershell
$env:PYTHONPATH='.'; uv run pytest -v
```

完整回归结果：

```text
41 passed
```
