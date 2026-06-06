# 工具异常与边界处理 Spec

## 背景与目标

Phase 8 的完整目标是补齐异常边界、缓存、日志、成本与安全能力。本 spec 只覆盖第一步：工具异常与边界处理。

参考文献 `docs/reference/22_工具异常与边界处理.md` 将边界问题分为三类：

- 数据为空：查询成功，但没有匹配数据。
- 工具执行出错：日期参数、数据库查询、工具内部逻辑等出现异常。
- 超出 Agent 能力范围：写操作、预测未来、发送邮件等非销售分析能力。

本次目标是让 5 个 LangChain 工具在空数据、参数错误、未知业务对象、数据库或内部异常时，都返回稳定、可读、便于大模型继续组织回答的中文提示；同时增加 FastAPI 全局异常处理器作为 HTTP 边界兜底，防止未捕获异常直接暴露内部细节或返回不稳定格式。

## In Scope

- 统一 5 个工具的错误返回语义和提示风格。
- 补齐空数据场景的明确提示，不返回空字符串、空列表或难以理解的异常文本。
- 区分参数错误、未知业务对象、无数据、权限限制、工具内部异常。
- 增加工具层边界测试，覆盖数据为空、日期错误、未知大区、未知销售员、未知图表维度组合、服务异常。
- 增加 FastAPI 全局异常处理器，捕获请求校验错误、HTTPException 和未处理异常。
- 统一本阶段 API 异常响应的最小结构，保证 HTTP 边界错误可预测。
- 验证 Agent system prompt 对超出能力范围请求的限制说明已经存在。
- 实现完成后，将代码编写过程同步到 `docs/process/`。

## Out of Scope

- Redis 缓存。
- 请求日志、工具调用日志、trace id。
- token 使用量与成本统计。
- 全量统一 API envelope，例如把所有成功响应也改造成 `{success, data, error}`。
- 修改数据库结构或测试数据。
- 引入新的第三方依赖。
- 让大模型生成 SQL 或执行写操作。

## 当前现状

当前工具已经有一部分边界处理：

- 日期解析错误会返回 `日期格式错误...` 或 `开始日期不能晚于结束日期`。
- 部分空数据场景会返回 `暂无订单数据`、`暂无趋势数据`、`暂无数据，无法生成图表`。
- 部分未知类型会返回 `未知汇总类型`、`未知趋势类型`、`未知图表类型`。
- 工具内部异常通常返回 `...时出现问题，请稍后重试`。
- system prompt 已声明：不能修改数据、不能预测未来、不能发送邮件。

仍需收敛的问题：

- 工具异常提示分散在各工具文件中，文案和分类不够统一。
- `analyze_sales_trend` 中未知大区当前通过 `RuntimeError` 进入通用异常，用户只能看到泛化错误，无法知道是大区名称错误。
- 图表工具中 `dimension=category` 与 `chart_type=bar`、`dimension=rep/category` 与 `chart_type=pie` 等组合行为不够显式。
- 服务异常、数据库异常等内部错误缺少统一的工具错误前缀，测试不容易稳定断言。

## 设计原则

### 1. 工具返回文本，而不是抛异常给 Agent

LangChain tool 面向 Agent 使用。工具内部应捕获可预期异常，并返回可读中文文本，让模型基于该文本生成友好回答。

工具不应向上抛出数据库异常、运行时异常或参数解析异常，除非是测试和开发阶段明确需要暴露的问题。

### 2. 全局异常处理器作为 HTTP 边界兜底

FastAPI 全局异常处理器用于处理工具层、Agent runtime、依赖注入或 API 层仍未捕获的异常。它是最后一道防线，不替代工具层的业务化错误文本。

当工具异常能在工具层处理时，HTTP 请求应继续走 Agent 链路，由 Agent 基于工具返回内容生成回答。当异常已经逃逸到 API 层时，全局异常处理器返回稳定 JSON，不把 Python exception、SQL、堆栈、数据库连接信息暴露给用户。

### 3. 错误信息对用户友好，对测试稳定

返回文本应包含稳定的错误标识前缀和中文说明：

```text
TOOL_EMPTY_DATA
...
```

```text
TOOL_INVALID_ARGUMENT
...
```

```text
TOOL_EXECUTION_ERROR
...
```

前缀用于测试断言和后续日志统计，中文说明用于 Agent 组织最终回答。

### 4. 区分“查不到对象”和“查不到数据”

示例：

- 未找到大区：`TOOL_UNKNOWN_ENTITY`。
- 已找到大区，但该时间段没有订单：`TOOL_EMPTY_DATA`。

这样 Agent 能向用户解释是名称可能写错，还是条件下确实没有数据。

### 5. 权限限制保持已有语义

已有权限类返回如 `NO_PERMISSION_REP_RANKING`、`NO_PERMISSION_REGION_RANKING` 应保留。它们不是工具执行失败，而是业务权限边界。

## 错误分类与返回格式

### 1. 空数据

格式：

```text
TOOL_EMPTY_DATA
在 {startDate} 至 {endDate} 期间，{scope}暂无{dataType}数据。
可能原因：该时段无交易、数据尚未录入，或查询条件过于严格。
```

适用场景：

- 订单查询无结果。
- 排名查询无结果。
- 趋势查询无结果。
- 图表数据源为空。
- 异常检测未发现异常时不使用该前缀，继续返回“当前数据未检测到明显异常...”，因为这是正常业务结果。

### 2. 参数错误

格式：

```text
TOOL_INVALID_ARGUMENT
日期格式错误，请使用 yyyy-MM-dd 格式，例如：2026-01-01。
```

或：

```text
TOOL_INVALID_ARGUMENT
日期范围错误，开始日期不能晚于结束日期。
```

适用场景：

- 日期缺失。
- 日期格式错误。
- 开始日期晚于结束日期。
- 工具参数组合不支持。

### 3. 未知业务对象

格式：

```text
TOOL_UNKNOWN_ENTITY
未找到大区：华中区。请确认名称是否正确，或改用可访问范围内的大区名称。
```

适用场景：

- 未知大区。
- 未知销售员。

### 4. 未知工具选项

由于当前工具 schema 已用 `Literal` 约束多数枚举值，非法枚举通常会被 Pydantic 拦截。若内部仍收到未知类型，返回：

```text
TOOL_INVALID_ARGUMENT
未知汇总类型，请使用 total、rep_ranking、region_ranking 或 product_ranking。
```

### 5. 工具内部异常

格式：

```text
TOOL_EXECUTION_ERROR
数据查询服务暂时不可用，请稍后重试。
```

适用场景：

- 数据库连接异常。
- Repository 或 Service 抛出未预期异常。
- 工具内部逻辑出现未预期异常。

内部异常不把 Python exception、SQL、堆栈、数据库连接信息返回给用户。

## API 异常响应格式

本次只统一异常响应，不改成功响应结构。

格式：

```json
{
  "success": false,
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "服务暂时不可用，请稍后重试"
  }
}
```

字段说明：

- `success`：固定为 `false`。
- `error.code`：稳定错误码，便于前端和测试断言。
- `error.message`：面向用户的中文提示。

错误码：

| HTTP 状态码 | code | 场景 |
| --- | --- | --- |
| 400 | `BAD_REQUEST` | 请求格式或参数语义错误 |
| 401 | `UNAUTHORIZED` | 未登录、令牌无效或令牌过期 |
| 403 | `FORBIDDEN` | 已登录但无权限 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 422 | `VALIDATION_ERROR` | FastAPI/Pydantic 请求体验证失败 |
| 500 | `INTERNAL_SERVER_ERROR` | 未处理异常、Agent runtime 异常、工具异常逃逸 |

说明：

- `HTTPException` 应保留原始 HTTP 状态码，并把 `detail` 转为 `error.message`。
- `RequestValidationError` 返回 `422` 和 `VALIDATION_ERROR`，message 使用简短中文提示，不直接返回完整内部错误结构。
- 未处理异常返回 `500` 和 `INTERNAL_SERVER_ERROR`。
- 流式接口如果已经开始返回 SSE，仍优先使用现有 `event: error` 事件；全局异常处理器只兜住响应开始前的异常。

## 工具级要求

### 1. `query_sales_orders`

必须处理：

- 日期错误返回 `TOOL_INVALID_ARGUMENT`。
- 未知大区返回 `TOOL_UNKNOWN_ENTITY`。
- 未知销售员返回 `TOOL_UNKNOWN_ENTITY`。
- 无订单返回 `TOOL_EMPTY_DATA`，并包含时间范围和查询范围。
- 内部异常返回 `TOOL_EXECUTION_ERROR`。

正常响应仍保留订单列表和小计。

### 2. `calculate_sales_summary`

必须处理：

- 日期错误返回 `TOOL_INVALID_ARGUMENT`。
- 未知大区返回 `TOOL_UNKNOWN_ENTITY`。
- 无排名数据返回 `TOOL_EMPTY_DATA`。
- `total` 汇总金额为 0 时不一定是错误，可以返回销售额 `¥0`；只有排名列表为空时返回空数据提示。
- 销售员越权查看团队或大区排名时保留 `NO_PERMISSION_*`。
- 内部异常返回 `TOOL_EXECUTION_ERROR`。

### 3. `analyze_sales_trend`

必须处理：

- 日期错误返回 `TOOL_INVALID_ARGUMENT`。
- 未知大区返回 `TOOL_UNKNOWN_ENTITY`，不能被泛化为内部异常。
- `mom`、`yoy` 对比周期无数据时保留“无法计算增长率”的业务提示。
- `monthly` 无趋势数据返回 `TOOL_EMPTY_DATA`。
- 内部异常返回 `TOOL_EXECUTION_ERROR`。

### 4. `generate_sales_chart`

必须处理：

- 日期错误返回 `TOOL_INVALID_ARGUMENT`。
- 未知大区返回 `TOOL_UNKNOWN_ENTITY`。
- 无图表数据返回 `TOOL_EMPTY_DATA`。
- 不支持的图表参数组合返回 `TOOL_INVALID_ARGUMENT`。
- 正常图表仍返回 `CHART_JSON:{...}`，不得给错误文本加 `CHART_JSON:` 前缀。
- 内部异常返回 `TOOL_EXECUTION_ERROR`。

参数组合规则：

- `line`：使用 `months` 和可选 `region_name`，忽略 `dimension`。
- `bar`：支持 `dimension=region` 或 `dimension=rep`。
- `pie`：支持 `dimension=region` 或 `dimension=category`。

### 5. `detect_sales_anomalies`

必须处理：

- 无异常时返回当前已有正常提示，不作为错误。
- 内部异常返回 `TOOL_EXECUTION_ERROR`。
- 权限过滤继续由 Service 层控制，普通销售员不返回其无权查看的全局异常。

## 公共实现建议

新增或扩展 `app/tools/formatting.py`，集中放置工具边界文案：

- `tool_empty_data(...)`
- `tool_invalid_argument(...)`
- `tool_unknown_entity(...)`
- `tool_execution_error(...)`
- `date_error_message(...)`

各工具只负责选择错误类型和填充上下文，不在每个文件里重复拼接前缀。

## 接口与 Agent 行为

HTTP 同步接口和流式接口的成功响应结构不在本 spec 中调整。

工具返回错误文本后：

- 同步接口仍返回 `200`，`reply` 中由 Agent 解释工具提示。
- 流式接口正常完成时仍发送 `done` 事件。
- 如果 Agent runtime 自身出现异常且未进入 SSE 输出，则由全局异常处理器返回稳定 JSON。
- 如果流式接口已经开始输出 SSE，则由流式生成器返回 `event: error`。

超出能力范围请求主要由 system prompt 约束。需要增加或保留测试确认 prompt 包含以下限制：

- 不能修改任何数据。
- 不能预测未来销售。
- 不能发送邮件、通知等外部操作。

## 验收标准

### 场景一：订单查询无数据

GIVEN 数据库中没有匹配时间和范围的订单  
WHEN 调用 `query_sales_orders`  
THEN 返回文本以 `TOOL_EMPTY_DATA` 开头，并说明可能原因。

### 场景二：日期格式错误

GIVEN start_date 为 `2026/01/01`  
WHEN 调用任意需要日期范围的工具  
THEN 返回文本以 `TOOL_INVALID_ARGUMENT` 开头，并给出 `yyyy-MM-dd` 示例。

### 场景三：日期范围错误

GIVEN start_date 晚于 end_date  
WHEN 调用任意需要日期范围的工具  
THEN 返回文本以 `TOOL_INVALID_ARGUMENT` 开头，并说明开始日期不能晚于结束日期。

### 场景四：未知大区

GIVEN region_name 为不存在的大区  
WHEN 调用订单、汇总、趋势或图表工具  
THEN 返回文本以 `TOOL_UNKNOWN_ENTITY` 开头，并说明未找到该大区。

### 场景五：未知销售员

GIVEN rep_name 为不存在的销售员  
WHEN 调用 `query_sales_orders`  
THEN 返回文本以 `TOOL_UNKNOWN_ENTITY` 开头，并说明未找到该销售员。

### 场景六：不支持的图表参数组合

GIVEN chart_type 为 `bar` 且 dimension 为 `category`  
WHEN 调用 `generate_sales_chart`  
THEN 返回文本以 `TOOL_INVALID_ARGUMENT` 开头，并说明柱状图支持的维度。

### 场景七：工具内部异常

GIVEN mock Service 抛出 RuntimeError  
WHEN 调用任意工具  
THEN 返回文本以 `TOOL_EXECUTION_ERROR` 开头，且不包含异常堆栈、SQL 或数据库连接信息。

### 场景八：无异常检测结果

GIVEN 当前可见数据没有明显异常  
WHEN 调用 `detect_sales_anomalies`  
THEN 返回“当前数据未检测到明显异常，销售数据运行正常。”，不返回错误前缀。

### 场景九：超范围请求约束

GIVEN system prompt 已构建  
WHEN 检查 prompt 文本  
THEN 包含不能修改数据、不能预测未来、不能发送邮件或通知的限制说明。

### 场景十：同步接口未捕获异常

GIVEN mock Agent runtime 抛出 RuntimeError  
WHEN 调用 `POST /agent/chat`  
THEN 返回 HTTP 500，响应体为 `success=false`，`error.code=INTERNAL_SERVER_ERROR`，且不包含异常堆栈。

### 场景十一：请求体验证失败

GIVEN `POST /agent/chat` 请求体缺少 `message`  
WHEN 调用接口  
THEN 返回 HTTP 422，响应体为 `success=false`，`error.code=VALIDATION_ERROR`。

## 预期修改文件

- `app/tools/formatting.py`
- `app/tools/sales_query_tool.py`
- `app/tools/sales_summary_tool.py`
- `app/tools/sales_trend_tool.py`
- `app/tools/chart_generator_tool.py`
- `app/tools/anomaly_detection_tool.py`
- `app/core/errors.py`
- `app/main.py`
- `tests/integration/test_sales_tools.py`
- `tests/integration/test_error_boundaries.py`
- `tests/unit/test_agent_prompt.py`
- `docs/process/008-tool-error-and-boundary-handling-process.md`

## 验收命令

```bash
$env:PYTHONPATH='.'; uv run pytest tests/integration/test_sales_tools.py tests/integration/test_error_boundaries.py tests/unit/test_agent_prompt.py -v
```

完整回归：

```bash
$env:PYTHONPATH='.'; uv run pytest -v
```

## 技术约束

- 不引入新依赖。
- 不改数据库结构。
- 不改成功 API response schema。
- 不改变 5 个工具的名称。
- 不改变权限过滤所在边界，权限仍由 Service 层执行。
- 不把内部异常细节返回给用户。
- 正常图表输出必须继续以 `CHART_JSON:` 开头。
