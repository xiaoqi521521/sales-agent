# API 契约规格说明

## 1. 通用约定

当前 API 直接挂载在根路径，不使用 `/api/v1` 前缀。

请求和响应使用 JSON。流式接口使用 SSE，响应类型为 `text/event-stream`。

受保护接口需要请求头：

```http
Authorization: Bearer <accessToken>
```

当前阶段暂不统一封装为 `{success, data, error}`。普通 JSON 接口使用明确 DTO 返回；错误主要使用 FastAPI 标准错误结构；SSE 使用事件协议表达结果和异常。

## 2. 健康检查

```text
GET /health
```

响应示例：

```json
{
  "name": "sales-agent",
  "version": "0.1.0",
  "status": "ok"
}
```

## 3. 登录

```text
POST /auth/login
```

请求体：

```json
{
  "repId": 2
}
```

成功响应：

```json
{
  "accessToken": "<jwt>",
  "tokenType": "bearer",
  "user": {
    "repId": 2,
    "username": "张伟",
    "role": "SALES_REP",
    "regionId": 1
  }
}
```

异常响应：

- `404`：销售员不存在。
- `422`：请求体校验失败。

## 4. 同步聊天

```text
POST /agent/chat
```

请求头：

```http
Authorization: Bearer <accessToken>
Content-Type: application/json
```

请求体：

```json
{
  "sessionId": "scenario-001",
  "message": "上个月华东区的销售情况怎么样？"
}
```

可选字段：

```json
{
  "userContext": {}
}
```

当前 `userContext` 是预留字段，运行时主要依赖 JWT 解析出的当前用户。

成功响应：

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

字段说明：

- `sessionId`：会话 ID，用于多轮上下文隔离。
- `reply`：Agent 最终回答。
- `durationMs`：本次请求耗时，单位毫秒。
- `toolCalls`：本轮工具调用摘要。
- `dataReferences`：数据引用预留字段，当前为空列表。

异常响应：

- `401`：未携带令牌、令牌无效或令牌过期。
- `422`：请求体校验失败，例如 `sessionId` 或 `message` 为空。
- `500`：模型、工具或数据库出现未处理异常。

## 5. 流式聊天

```text
POST /agent/chat/stream
```

请求头：

```http
Authorization: Bearer <accessToken>
Content-Type: application/json
```

请求体与同步聊天一致：

```json
{
  "sessionId": "scenario-001",
  "message": "上个月华东区的销售情况怎么样？"
}
```

响应格式为 SSE：

```text
event: <事件类型>
data: <JSON字符串>
```

### `token` 事件

用于返回模型生成的文本片段。

```text
event: token
data: {"content":"上个月"}
```

### `tool` 事件

用于返回工具调用完成后的摘要。

```text
event: tool
data: {"name":"calculate_sales_summary","summary":"销售额汇总：¥94,979 ..."}
```

### `done` 事件

用于返回流式输出完成后的最终结果。`done` 事件必须包含 `sessionId`，与同步接口保持一致。

```text
event: done
data: {"sessionId":"scenario-001","reply":"上个月华东区销售额为 ¥94,979，整体表现正常...","durationMs":1234,"toolCalls":[{"name":"calculate_sales_summary","summary":"销售额汇总：¥94,979 ..."}],"dataReferences":[]}
```

### `error` 事件

用于返回流式过程中的异常。

```text
event: error
data: {"message":"服务暂时不可用，请稍后重试"}
```

## 6. 持久化约定

同步接口正常完成后，会将用户消息、工具结果和 Agent 回答写入 MySQL `sa_chat_memory`。

流式接口正常完成并发送 `done` 事件后，也会写入 MySQL `sa_chat_memory`。

如果客户端在流式输出中途断开，生成器可能被取消，最后的持久化逻辑不保证执行。

## 7. 示例 curl

登录：

```bash
curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"repId":2}'
```

同步聊天：

```bash
curl -s -X POST "http://localhost:8000/agent/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <accessToken>" \
  -d '{"sessionId":"scenario-001","message":"上个月华东区的销售情况怎么样？"}'
```

流式聊天：

```bash
curl -N -X POST "http://localhost:8000/agent/chat/stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <accessToken>" \
  -d '{"sessionId":"scenario-001","message":"上个月华东区的销售情况怎么样？"}'
```
