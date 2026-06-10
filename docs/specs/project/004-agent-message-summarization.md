# Agent 消息摘要压缩 Spec

## 背景与目标

本阶段对应计划书 Phase 10：消息摘要压缩与 Token 成本控制。

此前曾考虑通过 Redis 缓存 Agent 最终回答来降低 token 成本，但该方案已放弃。原因是 Agent 回答强依赖用户权限、日期范围、查询范围、模型与提示词，缓存 key 离散度过高；如果再引入 LLM 或 embedding 做语义归一化，又会在命中率不确定时额外消耗 token。

本阶段只保留一个目标：

- 使用 LangChain 官方 `SummarizationMiddleware` 对长会话上下文做摘要压缩，减少后续请求携带的历史 token。

## In Scope

- 数据库会话记忆只保存 `user/assistant` 对话消息，不保存 `tool` 消息。
- `sa_chat_memory.messages` 与实际传给大模型的上下文保持一致。
- 每个 session 最多保存 20 条对话消息。
- 使用 LangChain 官方 `SummarizationMiddleware`。
- 当上下文达到 20 条消息时触发摘要。
- 摘要后保留最近 6 条对话消息。
- 摘要模型、触发消息数、保留消息数通过配置项控制。
- 补充摘要 middleware 配置测试、会话记忆测试、API/流式接口回归测试。

## Out of Scope

- 不实现 Redis 缓存。
- 不缓存 Agent 最终回答。
- 不实现 `QueryFingerprintService`。
- 不实现 `AgentAnswerCacheService`。
- 不做 LLM 语义归一化。
- 不做 embedding 相似度缓存。
- 不设计缓存 key、TTL、缓存命中/未命中链路。
- 不把完整工具结果放入下一轮上下文。

## 官方写法

通过 Context7 查询 LangChain 官方文档后，本项目采用 `langchain.agents.middleware.SummarizationMiddleware`，在 `create_agent(...)` 的 `middleware` 参数中接入。

配置形态：

```python
from langchain.agents.middleware import SummarizationMiddleware

SummarizationMiddleware(
    model="deepseek-v4-flash",
    trigger=("messages", 20),
    keep=("messages", 6),
)
```

说明：

- `trigger=("messages", 20)`：上下文达到 20 条消息时触发摘要。
- `keep=("messages", 6)`：摘要后保留最近 6 条原文对话消息。
- 本项目只把 `user/assistant` 写入数据库，因此这里的消息数与模型上下文消息数一致。

## 配置项

```env
AGENT_SUMMARY_MODEL=deepseek-v4-flash
AGENT_SUMMARY_TRIGGER_MESSAGES=20
AGENT_SUMMARY_KEEP_MESSAGES=6
```

说明：

- `AGENT_MEMORY_MAX_MESSAGES=20` 不作为环境配置项，当前阶段直接沿用 `ChatMemoryService(max_messages=20)` 的会话窗口规则。
- `AGENT_SUMMARY_ENABLED=true` 不作为环境配置项；Phase 10 的目标就是接入摘要 middleware，不额外增加启停开关。

## MySQL 会话记忆规则

`sa_chat_memory.messages` 保存 JSON 数组。

保存规则：

- 只保存 `role=user` 与 `role=assistant`。
- 不保存 `role=tool`。
- 最多保存最近 20 条消息。
- 工具调用结果仍可用于本轮 `toolCalls`、日志和 API 返回，但不进入长期会话记忆。

这样做的目的：

- 数据库存储内容与大模型上下文一致。
- 20 条消息触发条件不会被工具结果占用。
- 避免下一轮上下文中混入缺少 `tool_call_id` 的工具消息。

## 执行链路

### 同步接口

```text
POST /agent/chat
-> SalesAgentRuntime.chat_with_trace(...)
-> ChatMemoryService.get_context_messages(...)
-> 返回最近 user/assistant 历史
-> create_agent(..., middleware=[SummarizationMiddleware(...)])
-> Agent 执行
-> ChatMemoryService.append_turn(...)
-> 只保存 user 输入与 assistant 最终回答
```

### 流式接口

```text
POST /agent/chat/stream
-> SalesAgentRuntime.stream_chat(...)
-> ChatMemoryService.get_context_messages(...)
-> Agent 流式输出 token/tool/done 事件
-> 流式完成后保存 user 输入与 assistant 最终回答
-> 不保存 tool 事件内容到 sa_chat_memory.messages
```

### 长会话摘要

```text
上下文消息数达到 20
-> SummarizationMiddleware 触发
-> 较早消息被摘要压缩
-> 最近 6 条对话消息保留原文
-> 模型接收压缩后的上下文
```

## 拟调整文件

### `app/core/config.py`

新增或保留摘要配置项：

- `AGENT_SUMMARY_MODEL`
- `AGENT_SUMMARY_TRIGGER_MESSAGES`
- `AGENT_SUMMARY_KEEP_MESSAGES`

### `app/agent/memory.py`

调整：

- `StoredMessage` 不再接受 `tool` 作为长期记忆消息。
- `append_turn(...)` 只保存用户消息和 AI 最终回答。
- `get_context_messages(...)` 直接返回数据库中的对话消息，无需再过滤 `tool`。
- 保存前按 `ChatMemoryService(max_messages=20)` 截断。

### `app/agent/runtime.py`

调整：

- 初始化 Agent 时按配置接入 `SummarizationMiddleware`。
- 同步与流式接口都复用同一套记忆保存规则。
- 本轮工具调用仍可进入 `toolCalls` 返回结构，但不写入长期记忆。

### `tests/integration/test_agent_summarization.py`

新增：

- 验证 `SummarizationMiddleware` 使用 `trigger=("messages", 20)`。
- 验证 `SummarizationMiddleware` 使用 `keep=("messages", 6)`。
- 验证 `SummarizationMiddleware` 使用配置中的摘要模型。

### `tests/integration/test_agent_memory.py`

扩展：

- 验证数据库只保存 `user/assistant`。
- 验证 `tool` 消息不会进入 `sa_chat_memory.messages`。
- 验证最多保存 20 条对话消息。

### `tests/integration/test_agent_api.py` 与 `tests/integration/test_agent_streaming.py`

扩展：

- 验证 API 响应结构不因摘要配置改变。
- 验证流式接口完成后仍能保存用户消息和最终回答。

## 验收场景

### 场景一：数据库不保存 Tool 消息

GIVEN Agent 本轮调用了销售工具  
WHEN 本轮对话完成并保存记忆  
THEN `sa_chat_memory.messages` 中不存在 `role=tool`  
AND 数据库消息只包含 `user/assistant`。

### 场景二：最多保存 20 条对话消息

GIVEN 同一 session 已产生超过 20 条 `user/assistant` 消息  
WHEN 保存最新一轮对话  
THEN 数据库中只保留最近 20 条对话消息。

### 场景三：20 条消息触发摘要

GIVEN 当前上下文达到 20 条 `user/assistant` 消息  
WHEN Agent 执行  
THEN `SummarizationMiddleware` 按配置触发摘要  
AND 最近 6 条对话消息保留原文。

### 场景四：流式接口不缓存回答

GIVEN 调用 `/agent/chat/stream`  
WHEN Agent 正常完成  
THEN 系统不查询 Agent 回答缓存  
AND 系统不返回缓存命中事件  
AND 只保存用户消息和最终 assistant 回答。

## 非功能要求

- 不引入 Redis 作为 Phase 10 依赖。
- 不新增缓存管理 API。
- 摘要能力不改变同步接口和流式接口的响应结构。
- 长期记忆不得保存完整工具结果、JWT、API key 或数据库连接信息。
- 摘要配置必须可测试，避免后续误改阈值。

## 验收命令

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/integration/test_agent_summarization.py tests/integration/test_agent_memory.py tests/integration/test_agent_api.py tests/integration/test_agent_streaming.py -v
```

完整回归：

```powershell
$env:PYTHONPATH='.'; uv run pytest -v
```
