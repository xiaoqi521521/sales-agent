# 工具异常与边界处理编写过程

## 1. 任务范围

本阶段对应 Phase 8 的第一部分：工具异常与边界处理。

实际完成内容：

- 为 5 个 LangChain 工具统一工具错误返回前缀。
- 补齐空数据、日期错误、未知大区、未知销售员、图表参数组合不支持、内部执行异常等边界提示。
- 增加 FastAPI 全局异常处理器，作为 HTTP 边界兜底。
- 增加工具层和 API 层边界测试。

未纳入本阶段：

- Redis 缓存。
- 请求日志、工具调用日志、trace id。
- token 成本统计。
- 成功响应统一 envelope。
- 数据库结构调整。

## 2. 参考资料

主要参考：

- `docs/reference/00_SUMMARY.md`
- `docs/reference/22_工具异常与边界处理.md`
- `docs/specs/project/001-tool-error-and-boundary-handling.md`

参考文献 22 将边界问题分为三类：

- 数据为空：查询成功，但没有匹配数据。
- 工具执行出错：数据库、参数、工具内部逻辑异常。
- 超出 Agent 能力范围：写操作、预测未来、发送邮件等，由 system prompt 限制。

FastAPI 异常处理器写法通过 Context7 查询 FastAPI 官方文档确认，采用 `@app.exception_handler(...)` 注册 `HTTPException`、`RequestValidationError` 和兜底 `Exception` 处理器。

## 3. 测试先行

先补充失败测试，再实现代码。

新增或扩展测试：

- `tests/integration/test_sales_tools.py`
  - 空订单数据返回 `TOOL_EMPTY_DATA`。
  - 日期格式错误返回 `TOOL_INVALID_ARGUMENT`。
  - 日期范围错误返回 `TOOL_INVALID_ARGUMENT`。
  - 未知大区返回 `TOOL_UNKNOWN_ENTITY`。
  - 未知销售员返回 `TOOL_UNKNOWN_ENTITY`。
  - 不支持的图表参数组合返回 `TOOL_INVALID_ARGUMENT`。
  - 工具内部异常返回 `TOOL_EXECUTION_ERROR`，且不泄露异常细节。
- `tests/integration/test_error_boundaries.py`
  - `POST /agent/chat` 未捕获异常返回稳定 500 JSON。
  - 请求体验证失败返回稳定 422 JSON。
- `tests/unit/test_agent_prompt.py`
  - 确认 system prompt 包含不能发送邮件、通知等限制。

红灯验证时，目标测试出现 4 个失败，符合预期：

- 工具边界文本没有稳定前缀。
- 工具内部异常仍返回分散文案。
- API 未捕获异常返回默认 `Internal Server Error`。
- 请求体验证错误仍是 FastAPI 默认结构。

## 4. 工具层实现

在 `app/tools/formatting.py` 中集中新增工具错误 helper：

- `tool_empty_data(...)`
- `tool_invalid_argument(...)`
- `tool_unknown_entity(...)`
- `tool_execution_error(...)`
- `ToolBoundaryError`
- `ToolUnknownEntityError`

统一返回格式：

```text
TOOL_EMPTY_DATA
...
```

```text
TOOL_INVALID_ARGUMENT
...
```

```text
TOOL_UNKNOWN_ENTITY
...
```

```text
TOOL_EXECUTION_ERROR
...
```

这样做的原因：

- Agent 能拿到可读中文提示继续组织回答。
- 测试可以用稳定前缀断言。
- 后续如果要统计工具错误类型，可以直接识别前缀。

## 5. 各工具改造

### `query_sales_orders`

处理：

- 日期错误。
- 未知大区。
- 未知销售员。
- 查询结果为空。
- 内部异常。

正常订单返回结构保持不变。

### `calculate_sales_summary`

处理：

- 日期错误。
- 未知大区。
- 排名数据为空。
- 内部异常。

已有权限返回如 `NO_PERMISSION_REP_RANKING`、`NO_PERMISSION_REGION_RANKING` 保留不变。

### `analyze_sales_trend`

处理：

- 日期错误。
- 未知大区。
- 月度趋势为空。
- 内部异常。

未知大区不再被泛化成“获取趋势数据时出现问题”，而是明确返回 `TOOL_UNKNOWN_ENTITY`。

### `generate_sales_chart`

处理：

- 日期错误。
- 未知大区。
- 图表数据为空。
- 不支持的参数组合。
- 内部异常。

参数组合约束：

- `line` 使用 `months` 和可选 `region_name`。
- `bar` 只支持 `dimension=region` 或 `dimension=rep`。
- `pie` 只支持 `dimension=region` 或 `dimension=category`。

正常图表仍返回 `CHART_JSON:{...}`。

### `detect_sales_anomalies`

处理：

- 无异常时仍返回“当前数据未检测到明显异常，销售数据运行正常。”
- 内部异常返回 `TOOL_EXECUTION_ERROR`。

## 6. API 异常处理器

新增 `app/core/errors.py`。

注册的处理器：

- `StarletteHTTPException`
- `RequestValidationError`
- `Exception`

异常响应格式：

```json
{
  "success": false,
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "服务暂时不可用，请稍后重试"
  }
}
```

当前只统一异常响应，不改成功响应结构。

在 `app/main.py` 中调用 `register_exception_handlers(app)` 注册处理器。

## 7. 分层边界

本阶段保持以下边界：

- 工具内可预期异常优先在工具层转为文本。
- API 层异常处理器只兜住逃逸到 HTTP 边界的异常。
- Service 层继续负责权限过滤。
- Repository 层继续只负责数据库访问。
- 不把 Python exception、SQL、堆栈、数据库连接信息返回给用户。

## 8. 验证

目标测试命令：

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/integration/test_sales_tools.py tests/integration/test_error_boundaries.py tests/unit/test_agent_prompt.py -v
```

目标测试结果：

```text
8 passed
```

完整回归命令：

```powershell
$env:PYTHONPATH='.'; uv run pytest -v
```

完整回归结果以最终执行记录为准。
本次执行结果：

```text
34 passed
```
