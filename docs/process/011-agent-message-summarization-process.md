# Phase 10 消息摘要压缩代码编写过程

## 背景

Phase 10 最终放弃 Redis 缓存 Agent 回答的策略，只保留消息摘要压缩作为 token 成本控制手段。

本次实现目标：

- 数据库长期记忆只保存 `user/assistant`。
- `tool` 消息不进入 `sa_chat_memory.messages`。
- 使用 LangChain 官方 `SummarizationMiddleware`。
- 触发条件为 20 条对话消息。
- 摘要后保留最近 6 条对话消息。

## 参考文档

- `docs/specs/project/004-agent-message-summarization.md`
- `docs/agent_output/004-agent-answer-cache-decision-review.md`
- LangChain 官方 `SummarizationMiddleware` 文档，经 Context7 核实。

## 主要修改

### `app/core/config.py`

新增摘要配置：

```python
agent_summary_model: str = "deepseek-v4-flash"
agent_summary_trigger_messages: int = 20
agent_summary_keep_messages: int = 6
```

未新增 `AGENT_SUMMARY_ENABLED`，因为 Phase 10 的目标就是启用摘要能力。
未新增 `AGENT_MEMORY_MAX_MESSAGES`，继续沿用 `ChatMemoryService(max_messages=20)`。

### `app/agent/memory.py`

调整会话记忆规则：

- `get_messages(...)` 只接受历史中的 `user/assistant`。
- 历史脏数据里的 `tool` 会被丢弃。
- `append_turn(...)` 只追加本轮用户消息和 AI 最终回答。
- `tool_messages` 参数仍保留，用于兼容 runtime 调用，但不再写入数据库。
- `get_context_messages(...)` 直接返回数据库消息，因为数据库已经与模型上下文一致。

### `app/agent/runtime.py`

调整 Agent 初始化：

- 引入 LangChain 官方 `SummarizationMiddleware`。
- 在 `create_agent(...)` 参数中加入 `middleware=[SummarizationMiddleware(...)]`。
- 摘要配置使用：
  - `trigger=("messages", 20)`
  - `keep=("messages", 6)`
- 生产环境使用 OpenAI 兼容配置创建摘要模型，避免 `deepseek-v4-flash` 字符串被 LangChain 误判为 DeepSeek 官方 provider。
- 测试中如果传入的是假模型 `object()`，且没有 monkeypatch middleware，则跳过真实 middleware，避免测试被真实模型依赖绑定。

## 测试调整

### `tests/integration/test_agent_summarization.py`

新增摘要配置测试：

- 使用 monkeypatch 替换 `SummarizationMiddleware`。
- 验证传入参数为：
  - `model="deepseek-v4-flash"`
  - `trigger=("messages", 20)`
  - `keep=("messages", 6)`
- 验证 middleware 会传入 `create_agent(...)`。

### `tests/integration/test_agent_memory.py`

调整和新增记忆测试：

- 工具结果仍可转换为 `toolCalls` 返回给用户。
- 工具结果不再写入 `sa_chat_memory.messages`。
- 数据库只保存 `user/assistant`。
- 超过 20 条对话消息后，只保留最近 20 条。

## 执行链路

### 同步接口

```text
SalesAgentRuntime.chat_with_trace(...)
-> ChatMemoryService.get_context_messages(...)
-> 返回 user/assistant 历史
-> Agent 执行并可能调用工具
-> runtime 提取 tool_messages 用于 toolCalls
-> ChatMemoryService.append_turn(...)
-> 只保存 user + assistant
```

### 流式接口

```text
SalesAgentRuntime.stream_chat(...)
-> Agent 流式输出 token/tool/done
-> tool 事件仍返回给前端
-> 流式完成后 append_turn(...)
-> 只保存 user + assistant
```

### 摘要 middleware

```text
SalesAgentRuntime 初始化
-> 构造 SummarizationMiddleware
-> create_agent(..., middleware=[summary_middleware])
-> 上下文达到 20 条消息时由 LangChain 压缩较早消息
-> 最近 6 条消息保留原文
```

## 验证命令

已执行：

```powershell
uv run python -m pytest tests/integration/test_agent_summarization.py tests/integration/test_agent_memory.py tests/integration/test_agent_api.py tests/integration/test_agent_streaming.py -v
```

结果：

```text
9 passed
```
