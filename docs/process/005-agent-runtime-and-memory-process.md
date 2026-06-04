# Agent Runtime 与多轮记忆编写过程

本文档记录 Phase 5 的 Agent Runtime 和多轮记忆实现过程，说明参考资料、LangChain 官方写法、实现顺序和测试方式。

## 参考资料

本阶段先读取 `docs/reference/00_SUMMARY.md`，再加载 Phase 5 直接相关文献：

- `docs/reference/15_agent接口设计与工具层.md`
- `docs/reference/16_对话记忆接入.md`
- `docs/reference/19_场景实战一-简单查询与追问.md`
- `docs/reference/20_场景实战二-多步推理.md`

参考文献的核心要求是：

- Agent 是专业销售数据分析助手。
- Agent 绑定 5 个销售工具。
- 通过 `session_id` 隔离不同会话。
- 记忆保留最近 20 条消息。
- 对话记忆需要落到 `sa_chat_memory` 表。
- 追问时能继承上一轮的时间、区域、销售员、产品等上下文。

同时使用 Context7 查询 LangChain Python 官方文档，确认当前主流写法：

- 使用 `create_agent(...)` 创建 Agent。
- 调用时通过 `config={"configurable": {"thread_id": session_id}}` 标识会话。
- 当前项目默认不启用内存 checkpointer，而是从 MySQL `sa_chat_memory` 加载历史消息后传入 Agent。
- OpenAI 兼容模型使用 `init_chat_model(model_provider="openai", base_url=..., api_key=...)`。

## 依赖引入

通过 uv 引入 OpenAI 兼容模型依赖：

```bash
uv add langchain-openai
```

引入后更新：

- `pyproject.toml`
- `uv.lock`

## 编写顺序

1. 先写测试

   新增 `tests/unit/test_agent_prompt.py`，验证 system prompt 包含销售助手角色、当前日期、只读边界、中文回答、金额格式、`CHART_JSON:` 保留规则和追问上下文要求。

   新增 `tests/integration/test_agent_memory.py`，使用 SQLite 内存库和 fake agent 验证：

   - runtime 调用时传入 `thread_id=session_id`。
   - 默认不向 LangChain Agent 注入内存 checkpointer。
   - 同一 session 会加载上一轮 user/assistant 记忆。
   - 不同 session 相互隔离。
   - runtime 绑定 5 个销售工具。
   - 关键工具结果会写入 `sa_chat_memory`。

2. 创建提示词模块

   新增 `app/agent/prompts.py`，将参考文献中的 LangChain4j `@SystemMessage` 改写为 Python 字符串模板，并保留日期解释、能力边界、只读限制、中文回答和图表输出规则。

3. 创建记忆表模型和 repository

   新增 `app/models/chat_memory.py`，映射 `sa_chat_memory` 表。

   新增 `app/repositories/chat_memory_repository.py`，提供：

   - `find_by_session_id`
   - `save_messages`
   - `delete_by_session_id`

   同步更新 `app/db/schema.sql`，加入 MySQL DDL。

4. 创建记忆服务

   新增 `app/agent/memory.py`，用 JSON 保存最近 20 条消息。保存内容包括 user、assistant 和关键 tool 结果；再次调用模型时只把 user/assistant 历史作为上下文传入，避免缺少 tool_call_id 的 tool 历史干扰 LangChain 消息结构。

5. 创建 Agent Runtime

   新增 `app/agent/runtime.py`，负责：

   - 创建默认聊天模型。
   - 绑定 5 个销售工具。
   - 构造 system prompt。
   - 使用 `create_agent` 创建 LangChain Agent。
   - 调用时设置 `thread_id` 和 `recursion_limit=10`。
   - 从 LangChain 返回结果中提取最终回答和 ToolMessage。
   - 将用户消息、关键工具结果和 AI 回复写入记忆。

6. 创建 Agent schemas

   新增 `app/schemas/agent.py`，定义后续 API 阶段会使用的 `AgentChatRequest` 和 `AgentChatResponse`。

## 主要文件职责

### `app/agent/prompts.py`

集中维护销售 Agent 的 system prompt。后续权限阶段可以在这里扩展用户角色、大区范围等动态提示词内容。

### `app/agent/runtime.py`

Agent 编排入口。它不直接写销售查询逻辑，只负责把模型、prompt、tools、session memory 串起来。

### `app/agent/memory.py`

应用层会话记忆服务。当前用于持久化对话快照，保留最近 20 条消息。

### `app/models/chat_memory.py`

`sa_chat_memory` 表的 SQLAlchemy 映射。MySQL 中主键仍是 BIGINT；为了 SQLite 测试能自动生成主键，模型对 SQLite 使用 `Integer` 类型变体。

### `app/repositories/chat_memory_repository.py`

封装记忆表读写，避免 runtime 直接拼接数据库查询。

### `app/schemas/agent.py`

定义 Agent 聊天请求和响应对象。API 阶段会直接复用。

## 设计取舍

- Python 版使用 LangChain 官方 `create_agent`，不照搬 LangChain4j 的 `@AiService`。
- 运行态会话上下文以 MySQL `sa_chat_memory` 为准，runtime 每轮先读取历史，再把最新用户消息、关键工具结果和 AI 回复写回数据库。
- `checkpointer` 参数仅作为扩展点保留；默认不启用 `InMemorySaver`，避免生产记忆落在进程内存中。
- 测试不调用真实 LLM，而是注入 fake agent 验证 runtime、工具绑定、session 隔离和记忆落库。
- 当前还没有实现 HTTP Agent API 和流式输出，它们属于 Phase 6。

## 验证命令

Phase 5 验收命令：

```bash
uv run python -m pytest tests\unit\test_agent_prompt.py tests\integration\test_agent_memory.py -v
```

完整集成测试：

```bash
uv run python -m pytest tests\unit tests\integration -v
```

当前 Phase 5 单点验证结果为 `4 passed`，`tests/unit` + `tests/integration` 完整验证结果为 `18 passed`。
