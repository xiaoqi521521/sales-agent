# Agent API 与流式输出编写过程

本文档记录 Phase 6 的同步聊天接口和 SSE 流式输出接口实现过程，说明参考资料、LangChain 官方流式写法、接口契约和验证方式。

## 参考资料

本阶段先读取 `docs/reference/00_SUMMARY.md`，再加载 Phase 6 直接相关文献：

- `docs/reference/17_agent controller与端到端测试.md`
- `docs/reference/18_流式输出实现.md`

参考文献的核心要求是：

- 暴露同步聊天接口。
- 暴露流式聊天接口。
- 请求体包含 `sessionId` 和 `message`。
- 同步响应包含 `sessionId`、回答文本和耗时。
- 流式接口使用 SSE，逐步输出 token，并在结束时发送 done 事件。

同时使用 Context7 查询 LangChain Python 官方文档，确认当前流式写法：

- 使用 `agent.stream(...)` / `agent.astream(...)`。
- 使用 `stream_mode=["messages", "updates"]` 同时获取 token 和工具进度。
- 使用 `version="v2"` 获取结构化 stream chunk。
- `messages` 事件中读取模型 token，`updates` 事件中读取工具结果和模型完成消息。

## 编写顺序

1. 先写测试

   新增 `tests/integration/test_agent_api.py`，通过 FastAPI dependency override 注入 fake runtime，验证：

   - `POST /agent/chat` 返回 `sessionId`、`reply`、`durationMs`、`toolCalls`、`dataReferences`。
   - 请求体为空时返回 422。

   新增 `tests/integration/test_agent_streaming.py`，验证：

   - `POST /agent/chat/stream` 返回 `text/event-stream`。
   - SSE 事件包含 `token`、`tool`、`done`。
   - runtime 异常时返回统一 `error` 事件。

2. 扩展 Agent Runtime

   在 `app/agent/runtime.py` 中新增：

   - `ToolCallTrace`
   - `AgentRunResult`
   - `chat_with_trace(...)`
   - `stream_chat(...)`

   `chat(...)` 继续保留原有字符串返回，避免影响 Phase 5 测试和后续内部调用；API 层使用 `chat_with_trace(...)` 获取更完整的响应结构。

3. 创建 SSE 事件格式化模块

   新增 `app/agent/streaming.py`：

   - `AgentStreamEvent`
   - `format_sse_event(...)`

   当前事件 data 统一编码为紧凑 JSON，便于前端解析和测试断言。

4. 创建 FastAPI Agent endpoint

   新增 `app/api/v1/endpoints/agent.py`：

   - `POST /agent/chat`
   - `POST /agent/chat/stream`

   再由 `app/api/v1/router.py` 挂载到应用根路径下，最终路径为：

   - `POST /agent/chat`
   - `POST /agent/chat/stream`

5. 创建 runtime dependency

   在 `app/api/dependencies.py` 中新增 `get_sales_agent_runtime(...)`，通过 `get_db_session` 注入 `AsyncSession`，再创建 `SalesAgentRuntime`。

6. 扩展 Agent schemas

   更新 `app/schemas/agent.py`：

   - `AgentChatRequest`
   - `AgentToolCallSummary`
   - `AgentChatResponse`

   请求字段保留 Java 参考项目风格 alias：`sessionId`、`userContext`。

## 主要文件职责

### `app/api/v1/endpoints/agent.py`

API 层入口。只负责请求校验、调用 runtime、组织响应和 SSE 包装，不直接访问数据库或工具层。

### `app/agent/runtime.py`

Agent 执行入口。同步路径负责返回最终回答和工具摘要；流式路径负责解析 LangChain stream chunk，输出 token/tool/done 事件，并在结束后写入 MySQL 记忆。

### `app/agent/streaming.py`

SSE 事件格式化。当前事件类型：

- `token`：模型生成的文本片段。
- `tool`：工具调用结果摘要。
- `done`：最终完整回答、耗时、工具摘要和数据引用占位。
- `error`：统一错误事件。

### `app/schemas/agent.py`

Agent API 的请求响应 DTO。它面向 HTTP API，不直接绑定 LangChain 内部消息结构。

## 设计取舍

- 流式接口采用 SSE，而不是 WebSocket；当前需求是单向输出 token，SSE 更轻。
- API 测试使用 fake runtime，不调用真实 LLM，避免测试依赖 API key 和网络。
- `dataReferences` 当前保留为空列表，后续可在工具层增加结构化数据引用后填充。
- 流式事件 data 使用 JSON，而不是裸字符串，便于前端稳定消费。

## 验证命令

Phase 6 验收命令：

```bash
uv run python -m pytest tests\integration\test_agent_api.py tests\integration\test_agent_streaming.py -v
```

完整验证：

```bash
uv run python -m pytest tests\unit tests\integration -v
```

当前 Phase 6 单点验证结果为 `4 passed`，`tests/unit` + `tests/integration` 完整验证结果为 `22 passed`。
