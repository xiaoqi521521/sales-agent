# Agent 数据结构说明

本文档说明当前项目中三类核心数据结构：

- 数据库存储的会话结构
- 发给大模型的上下文结构
- Agent 返回给用户的同步与流式响应结构

## 1. 数据库存储会话结构

会话记忆存储在 MySQL 表 `sa_chat_memory` 中。

表结构：

```sql
CREATE TABLE IF NOT EXISTS sa_chat_memory (
    id BIGINT NOT NULL AUTO_INCREMENT,
    session_id VARCHAR(100) NOT NULL COMMENT '会话 ID',
    messages LONGTEXT NOT NULL COMMENT '序列化的消息列表（JSON）',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话记忆持久化';
```

其中 `messages` 是 JSON 字符串，当前保存最近 20 条消息。

结构示例：

```json
[
  {
    "role": "user",
    "content": "上个月华东区的销售情况怎么样？"
  },
  {
    "role": "tool",
    "content": "销售额汇总：¥94,979 ...",
    "name": "calculate_sales_summary"
  },
  {
    "role": "assistant",
    "content": "上个月华东区销售额为 ¥94,979，整体表现正常..."
  }
]
```

保存顺序：

```text
user -> tool（如果本轮调用了工具）-> assistant
```

字段含义：

- `role=user`：用户输入。
- `role=tool`：工具调用结果，额外带 `name` 表示工具名称。
- `role=assistant`：Agent 最终回答。

## 2. 大模型上下文结构

虽然数据库中保存了 `user`、`tool`、`assistant` 三类消息，但当前发给大模型的上下文会过滤掉 `tool`。

实际传给 LangChain Agent 的 payload 类似：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "上一轮用户问题"
    },
    {
      "role": "assistant",
      "content": "上一轮AI回答"
    },
    {
      "role": "user",
      "content": "本轮用户问题"
    }
  ]
}
```

运行配置：

```python
config = {
    "configurable": {"thread_id": session_id},
    "recursion_limit": 10,
}
```

当前策略：

- MySQL 保存完整历史，包括工具结果。
- 大模型上下文只使用 `user` 和 `assistant`。
- `tool` 结果用于追踪、接口摘要和持久化，不直接进入下一轮模型上下文。

## 3. 同步接口返回结构

同步聊天接口：

```text
POST /agent/chat
```

响应结构：

```json
{
  "sessionId": "scenario-001",
  "reply": "上个月华东区销售额为 ¥94,979，整体表现正常...",
  "durationMs": 1234,
  "toolCalls": [
    {
      "name": "calculate_sales_summary",
      "summary": "销售额汇总：¥94,979 ..."
    }
  ],
  "dataReferences": []
}
```

字段含义：

- `sessionId`：会话 ID。
- `reply`：AI 最终回答文本。
- `durationMs`：本次请求耗时，单位毫秒。
- `toolCalls`：本轮工具调用摘要。
- `dataReferences`：数据引用预留字段，当前为空列表。

## 4. 流式接口返回结构

流式聊天接口：

```text
POST /agent/chat/stream
```

返回格式为 SSE，每个事件形如：

```text
event: <事件类型>
data: <JSON字符串>
```

### token 事件

模型生成的文本片段。

```text
event: token
data: {"content":"上个月"}
```

### tool 事件

工具调用完成后的摘要。

```text
event: tool
data: {"name":"calculate_sales_summary","summary":"销售额汇总：¥94,979 ..."}
```

### done 事件

流式输出完成后的最终结果。当前 `done` 事件已与同步接口对齐，包含 `sessionId`。

```text
event: done
data: {"sessionId":"scenario-001","reply":"上个月华东区销售额为 ¥94,979，整体表现正常...","durationMs":1234,"toolCalls":[{"name":"calculate_sales_summary","summary":"销售额汇总：¥94,979 ..."}],"dataReferences":[]}
```

### error 事件

流式过程中出现异常时返回。

```text
event: error
data: {"message":"服务暂时不可用，请稍后重试"}
```

## 5. 流式结果是否持久化

流式接口正常完整执行并发送 `done` 事件时，会将本轮对话写入 MySQL `sa_chat_memory.messages`。

写入内容包括：

```text
用户消息 user
工具结果 tool
AI 最终回答 assistant
```

注意：如果客户端在流式输出中途断开，生成器可能被取消，最后的持久化逻辑不一定执行。正常完成并发出 `done` 事件时，会持久化。

## 6. 简单总结

```text
数据库：保存完整历史 user/tool/assistant
模型上下文：只发送 user/assistant
同步接口：返回 sessionId/reply/durationMs/toolCalls/dataReferences
流式接口：逐步返回 token/tool，最终 done 返回 sessionId/reply/durationMs/toolCalls/dataReferences
```
