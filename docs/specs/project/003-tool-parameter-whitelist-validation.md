# 工具参数白名单校验 Spec

## 背景与目标

本阶段对应计划书 Phase 11 的“SQL 注入防护与参数白名单”。本次只完成其中的工具参数白名单校验，粒度对齐 `docs/reference/26_SQL注入防护.md` 中的“防护措施二：工具层参数白名单校验”。

当前项目 Repository 层已经使用 SQLAlchemy 表达式和参数绑定，不会把工具字符串参数拼接进 SQL。本阶段不重写查询层，也不扩大安全设计范围，只在工具入口对高风险、有限取值或有明确格式的参数做校验：

- 日期字符串。
- 大区名称。
- 图表类型。
- 图表维度。
- TopN、limit、months 等数值边界。

如果参数不合法，不能静默修正为合法值，例如不能把 `top_n=0` 自动改成 `1`，也不能把 `limit=1000` 自动压成 `50`。参数错误应在 Pydantic `args_schema` 阶段提前抛出，工具函数不执行，不打印工具开始/结束日志。

Pydantic 参数异常不在具体工具函数内部捕获，而是在 Agent/LangChain 工具调用边界统一捕获并转换为可读错误。这样既能阻止非法参数进入工具业务逻辑，又能避免异常裸露到 HTTP 层变成 500。

## 参考资料

- `docs/reference/00_SUMMARY.md`
- `docs/reference/26_SQL注入防护.md`
- `docs/plans/001-sales-agent-refactor-master-plan.md`

Context7 已核实 Pydantic v2 主流用法：

- 简单数值和长度约束可以使用 `Field(...)`。
- 自定义字段校验可以使用 `@field_validator(...)`。

本阶段采用 Pydantic 作为唯一工具参数白名单校验入口。工具函数内部不重复做同类参数校验，只保留业务边界处理，例如空数据、实体不存在、权限不足、服务异常。

## In Scope

- 修改 `app/tools/schemas.py`，通过 Pydantic `Field`、`Literal`、`field_validator` 实现工具参数白名单校验。
- 参数非法时由 Pydantic 抛出 `ValidationError`，工具函数不执行。
- 在 Agent/LangChain 工具调用边界统一捕获参数校验异常，并转换为模型或用户可理解的错误信息。
- 替换当前对数值参数的静默 `clamp(...)` 行为，越界参数在 schema 阶段失败。
- 增加参数校验测试，覆盖参考文献防护措施二中的日期、大区、图表类型、维度和 TopN。
- 增加 SQL 注入形态的大区名称测试，验证工具函数不会执行。
- 同步编写 `docs/process/010-tool-parameter-whitelist-validation-process.md`。

## Out of Scope

- 不新增数据库表。
- 不新增依赖。
- 不实现 Redis 缓存。
- 不引入 NL2SQL。
- 不新增模型生成 SQL 或执行任意 SQL 的能力。
- 不重写 Repository 查询层。
- 不新增 `app/tools/validation.py`。
- 不在工具函数内部重复校验 Pydantic 已经约束的参数。
- 不在工具函数内部捕获 Pydantic `ValidationError`。
- 不要求非法参数时打印 `tool_call_started` 或 `tool_call_completed`。
- 不对明显不需要校验的字段扩大规则，例如 `customer_name` 和 `title`。
- 不把销售员名称做白名单校验；销售员是否存在仍由 Service/Repository 判断。
- 不修改鉴权和角色权限模型。

---

## 当前状态

### 已具备

当前 Repository 层主要使用 SQLAlchemy 表达式：

```python
select(SalesRegion).where(SalesRegion.name == name)
select(SalesOrder).where(SalesOrder.order_date.between(start, end))
```

这种写法会由 SQLAlchemy 和数据库驱动做参数绑定，不会把字符串参数拼接成 SQL 结构。

当前 `app/tools/schemas.py` 已经有部分枚举约束：

- `summary_type: Literal["total", "rep_ranking", "region_ranking", "product_ranking"]`
- `trend_type: Literal["mom", "yoy", "monthly"]`
- `chart_type: Literal["line", "bar", "pie"]`
- `dimension: Literal["region", "rep", "category"]`

### 待补齐

- 日期格式校验分散在工具内部。
- `limit`、`top_n`、`months` 当前存在静默修正行为。
- `region_name` 还没有按参考文献方式做明确白名单校验。
- 缺少恶意大区名称回归测试。

---

## 参数校验范围

### 1. 日期参数

适用字段：

- `start_date`
- `end_date`
- `current_start`
- `current_end`
- `previous_start`
- `previous_end`

规则：

- 非空日期必须符合 `yyyy-MM-dd`。
- 必填日期缺失时由 Pydantic 判定为参数错误。
- 同一日期范围内，开始日期不能晚于结束日期。
- 可选日期为空时保留现有工具语义，例如趋势工具可自动推导上一个周期。

非法示例：

```text
2026/01/01
2026-13-01
2026-02-01 至 2026-01-01
```

### 2. 大区名称

适用字段：

- `region_name`

规则：

- `None` 或空字符串表示不限制。
- 非空时先 `strip()`。
- 必须属于允许的大区名称集合。

本项目测试数据中的允许值暂定为：

```text
华东区
华南区
华北区
西南区
```

非法示例：

```text
"'; DROP TABLE sales_order; --"
"不存在的大区"
```

说明：

此处粒度对齐参考文献防护措施二，对 `regionName` 做明确白名单。销售员名称暂不做同类白名单，因为参考文献没有要求，且销售员属于更频繁变化的数据实体，仍由 Service/Repository 判断是否存在和是否可见。

### 3. 图表类型

适用字段：

- `chart_type`

允许值：

```text
line
bar
pie
```

非法值由 Pydantic 校验失败拦截。

### 4. 图表维度

适用字段：

- `dimension`

允许值：

```text
region
rep
category
```

非法值由 Pydantic 校验失败拦截。

### 5. 数值参数

适用字段：

| 字段 | 规则 | 说明 |
| --- | --- | --- |
| `limit` | 1 到 50 | 订单明细最多返回 50 条 |
| `top_n` | 1 到 20，或 -20 到 -1 | 产品排名可用负数表示最差 N 名；0 非法 |
| `months` | 1 到 24 | 月度趋势最多查看 24 个月 |

规则：

- 越界时由 Pydantic 校验失败拦截。
- 不再静默 clamp。

---

## 不做校验的参数

### `customer_name`

不做白名单校验。

原因：

- 当前 `customer_name` 不进入 Repository 拼 SQL。
- 当前逻辑是在已查询出的订单结果中做内存包含判断。
- 客户名称本身可能包含英文、数字、空格或符号，过度校验容易误伤正常数据。

### `title`

不做白名单校验。

原因：

- 图表标题只用于返回文本，不参与 SQL 查询。
- 参考文献防护措施二没有覆盖标题字段。

### `rep_name`

不做白名单校验。

原因：

- 参考文献防护措施二只明确校验 `regionName`。
- 销售员姓名属于人员数据，可能随测试数据或真实数据变化。
- 是否存在、是否在权限范围内继续交给 Service/Repository 处理。

---

## 拟新增或调整文件

### `app/tools/schemas.py`

职责：

- 作为 LangChain tools 的唯一参数白名单校验入口。
- 使用 Pydantic v2 的 `Field`、`Literal`、`field_validator` 做参数约束。

预计调整：

- 为 `limit` 增加 `Field(ge=1, le=50)`。
- 为 `months` 增加 `Field(ge=1, le=24)`。
- 为 `top_n` 增加 `Field(ge=-20, le=20)`，并通过 `field_validator` 禁止 0。
- 为日期字段增加 `yyyy-MM-dd` 格式校验。
- 为 `region_name` 增加白名单校验。
- 继续保留 `summary_type`、`trend_type`、`chart_type`、`dimension` 的 `Literal` 约束。

### `app/tools/*_tool.py`

职责：

- 删除或弱化与 schema 重复的静默修正逻辑。
- 保留业务边界处理，例如数据为空、实体不存在、权限不足、服务异常。
- 参数非法时工具函数不会执行，因此不在工具内捕获 Pydantic `ValidationError`。

### Agent/LangChain 工具调用边界

预计调整位置以现有 agent 创建和执行代码为准，优先复用当前项目已有的工具异常处理边界。

职责：

- 捕获 Pydantic 参数校验异常。
- 将异常转换为可读错误，例如“工具参数不合法，请检查日期格式、大区名称、图表类型或数值范围”。
- 不把完整恶意参数原样输出到控制台日志或最终回答。
- 不把参数校验失败当成工具函数已执行处理，因此不补打 `tool_call_started` / `tool_call_completed`。

### `app/tools/formatting.py`

本阶段不要求新增参数校验 helper。

### 测试文件

新增或扩展：

- `tests/unit/test_input_validation.py`
- `tests/integration/test_sales_tools.py`

测试重点：

- schema 层非法输入会抛 Pydantic `ValidationError`。
- 非法参数不会触发工具函数体内的业务逻辑。
- Agent/LangChain 工具调用边界能把参数校验异常转换为可读错误，不返回 HTTP 500。
- 合法参数仍能正常进入业务查询。

---

## 执行链路

### 正常链路

```text
用户问题
-> LLM 选择工具并生成参数
-> LangChain 根据 args_schema 调用 Pydantic 校验
-> 校验通过
-> 工具函数开始执行
-> tool_call_started(...)
-> Service 解析实体和权限范围
-> Repository 使用 SQLAlchemy 表达式和参数绑定查询
-> tool_call_finished(..., result)
-> 返回工具结果
```

### 非法参数链路

```text
用户问题
-> LLM 生成非法参数
-> LangChain 根据 args_schema 调用 Pydantic 校验
-> Pydantic 抛 ValidationError
-> 工具函数不执行
-> 不打印 tool_call_started / tool_call_completed
-> Agent/LangChain 工具调用边界捕获参数校验异常
-> 转换为可读错误，提示检查日期、大区、图表类型、维度或数值范围
-> API 层正常返回错误说明，不暴露内部异常堆栈
```

---

## 验收场景

### 场景一：大区名包含 SQL 片段

GIVEN `region_name="'; DROP TABLE sales_order; --"`  
WHEN 使用工具 `args_schema` 校验参数  
THEN Pydantic 抛 `ValidationError`  
AND 工具函数不执行  
AND Agent/LangChain 工具调用边界返回可读参数错误。

### 场景二：未知大区名称

GIVEN `region_name="不存在的大区"`  
WHEN 使用工具 `args_schema` 校验参数  
THEN Pydantic 抛 `ValidationError`。

如果通过 Agent 端到端触发该错误，最终结果应是可读参数错误，不应返回 HTTP 500。

说明：此处按参考文献防护措施二处理，`region_name` 先过白名单，未知大区不再进入业务实体解析。

### 场景三：非法图表类型

GIVEN `chart_type="scatter"`  
WHEN 使用 `SalesChartInput` 校验参数  
THEN Pydantic 抛 `ValidationError`。

### 场景四：非法维度

GIVEN `dimension="amount"`  
WHEN 使用 `SalesChartInput` 校验参数  
THEN Pydantic 抛 `ValidationError`。

### 场景五：日期格式错误

GIVEN `start_date="2026/01/01"`  
WHEN 使用对应工具 schema 校验参数  
THEN Pydantic 抛 `ValidationError`，提示使用 `yyyy-MM-dd`。

如果通过 Agent 端到端触发该错误，最终结果应提示日期格式错误，不应进入工具业务逻辑。

### 场景六：日期顺序错误

GIVEN `start_date="2026-02-01"`，`end_date="2026-01-01"`  
WHEN 使用对应工具 schema 校验参数  
THEN Pydantic 抛 `ValidationError`。

如果通过 Agent 端到端触发该错误，最终结果应提示日期范围错误，不应进入工具业务逻辑。

### 场景七：数值越界

GIVEN `limit=1000`  
WHEN 使用 `SalesQueryInput` 校验参数  
THEN Pydantic 抛 `ValidationError`。

如果通过 Agent 端到端触发该错误，最终结果应提示数值范围错误，不应把 `limit` 静默修正为合法值。

GIVEN `months=100`  
WHEN 使用趋势或图表 schema 校验参数  
THEN Pydantic 抛 `ValidationError`。

GIVEN `top_n=0`  
WHEN 使用 `SalesSummaryInput` 校验参数  
THEN Pydantic 抛 `ValidationError`。

### 场景八：合法参数正常执行

GIVEN `region_name="华东区"`  
WHEN 使用销售查询工具  
THEN schema 校验通过，并正常进入工具函数。

GIVEN `chart_type="bar"`，`dimension="region"`  
WHEN 使用图表工具  
THEN schema 校验通过，并正常返回图表数据。

---

## 非功能要求

- 不新增依赖。
- 不打印完整恶意参数到控制台日志。
- 不改变现有成功返回结构。
- 不改变权限过滤规则。
- 参数校验失败不应变成 HTTP 500。
- 不把工具参数白名单写死到 prompt 中作为唯一防线。
- 参数校验逻辑可单元测试，不依赖真实大模型。

## 风险与取舍

### 1. 为什么不校验所有字符串

因为本阶段粒度对齐参考文献防护措施二，只校验明确高风险或有限取值的参数。过度校验客户名、标题、销售员名会增加误伤，且这些字段当前不参与 SQL 拼接。

### 2. 为什么不静默修正参数

静默修正会隐藏模型生成错误，也会让用户误以为查询条件被完整执行。本阶段要求非法参数显式失败。

### 3. 为什么统一使用 Pydantic

Pydantic 是工具参数 schema 的主入口，和 LangChain `args_schema` 天然集成。非法参数在工具执行前失败，能更早阻断风险路径；工具没有真正执行时，也不要求打印工具开始和结束日志。

### 4. 为什么不在工具内部捕获 Pydantic 异常

Pydantic 参数异常发生在 `args_schema` 阶段，此时工具函数还没有开始执行。把捕获逻辑写进工具函数内部既捕获不到这类前置异常，也会模糊“参数校验”和“业务执行”的边界。

本阶段采用的边界是：Pydantic 负责参数入口校验；工具函数只负责业务逻辑；Agent/LangChain 工具调用边界负责把参数校验异常转换成可读错误。这样参数错误不会进入业务层，也不会以未处理异常的形式暴露给 HTTP 调用方。

## 实施后同步文档

实现完成后需要同步：

- `docs/process/010-tool-parameter-whitelist-validation-process.md`
- `docs/plans/001-sales-agent-refactor-master-plan.md` 中 Phase 11 任务状态

## 验收命令

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/unit/test_input_validation.py tests/integration/test_sales_tools.py -v
```

完整回归：

```powershell
$env:PYTHONPATH='.'; uv run pytest -v
```
