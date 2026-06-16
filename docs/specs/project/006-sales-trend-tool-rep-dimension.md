# Sales Trend Tool Rep Dimension Spec

## 背景与目标

当前 `analyze_sales_trend` 工具支持三类趋势分析：

- `mom`：环比分析
- `yoy`：同比分析
- `monthly`：近 N 个月月度趋势

但工具参数只支持 `region_name`，不能指定 `rep_name`。因此当用户提出“本季度掉量最大的销售员是谁，分析一下原因”这类问题时，Agent 虽然可以通过 `calculate_sales_summary` 对比两个季度的销售员排行，再通过 `query_sales_orders` 查询订单明细，但无法调用趋势工具对某个销售员做标准化的周期趋势分析。

本阶段目标是增强趋势工具，使其支持销售员维度：

- `analyze_sales_trend` 增加 `rep_name` 参数。
- `mom` 和 `yoy` 支持按销售员计算销售额对比。
- `monthly` 支持按销售员返回月度趋势。
- 权限过滤仍由 `SalesQueryService` 统一执行，工具层不绕过 Service。
- 不调整 `months` 默认值，本 spec 不处理默认月份策略。

## In Scope

- 修改 `SalesTrendInput`，增加可选 `rep_name` 参数。
- 修改 `create_sales_trend_tool`，把 `rep_name` 纳入工具签名、日志参数和解析流程。
- 支持以下查询范围：
  - 全公司趋势：未传 `region_name`、未传 `rep_name`。
  - 大区趋势：传 `region_name`，不传 `rep_name`。
  - 销售员趋势：传 `rep_name`，可选同时传 `region_name` 作为进一步限定。
- `mom` / `yoy` 在销售员维度下调用按销售员汇总能力。
- `monthly` 在销售员维度下调用按销售员月度趋势能力。
- 当销售员不存在、不可见或越权时，返回稳定的 `TOOL_UNKNOWN_ENTITY` 或空数据提示，不泄露越权数据。
- 增加集成测试覆盖销售员维度趋势分析。

## Out of Scope

- 不修改 `months` 默认值。
- 不新增单独的“掉量最大销售员”工具。
- 不修改 Agent prompt。
- 不修改数据库表结构。
- 不引入新的权限模型。
- 不让工具层直接访问数据库绕过 Service。

## 设计

### 工具参数

`SalesTrendInput` 增加：

```python
rep_name: str | None = Field(
    default=None,
    description="销售员姓名；空字符串或 null 表示不限销售员",
)
```

工具函数签名调整为：

```python
async def analyze_sales_trend(
    trend_type: str,
    current_start: str | None = None,
    current_end: str | None = None,
    previous_start: str | None = None,
    previous_end: str | None = None,
    region_name: str | None = None,
    rep_name: str | None = None,
    months: int = 6,
) -> str:
```

### 范围解析

新增统一解析函数，例如：

```python
async def _resolve_scope(service, session, region_name, rep_name):
    ...
```

返回：

```python
Scope(region_id: int | None, rep_id: int | None, label: str)
```

解析规则：

- `region_name` 为空时，`region_id=None`。
- `rep_name` 为空时，`rep_id=None`。
- `rep_name` 非空时，通过 `service.get_rep_id_by_name(...)` 解析。
- `service.get_rep_id_by_name(...)` 已受当前用户权限上下文约束；不可见销售员返回 `None`。
- 如果销售员不可见，工具返回销售员未知/不可访问提示。
- 如果同时传 `region_name` 和 `rep_name`，Service 解析销售员时仍要保证该销售员在当前可见范围内；必要时可通过订单查询或仓储能力确认销售员和大区一致。

### Service 能力

当前已有能力：

- `SalesQueryService.get_rep_id_by_name(...)`
- `SalesQueryService.get_region_id_by_name(...)`
- `SalesOrderRepository.sum_amount_by_rep(...)`
- `SalesOrderRepository.find_monthly_trend_by_rep(...)`

建议在 Service 层补充更清晰的封装，避免工具直接访问 repository：

```python
async def query_total_amount_by_rep(
    self,
    session: AsyncSession,
    rep_id: int,
    start: date,
    end: date,
) -> Decimal:
    ...
```

```python
async def query_monthly_trend_by_rep(
    self,
    session: AsyncSession,
    rep_id: int,
    months: int,
    today: date | None = None,
) -> list[MonthlyTrendDTO]:
    ...
```

这两个方法应继续遵守当前用户权限：

- 销售员只能查询自己。
- 主管只能查询本大区销售员。
- 总监可以查询任意销售员。
- 越权时返回 `Decimal("0")` 或空列表，工具再转成稳定提示。

### 趋势计算

`mom` 销售员维度：

```text
当前周期销售额 = query_total_amount_by_rep(rep_id, current_start, current_end)
对比周期销售额 = query_total_amount_by_rep(rep_id, previous_start, previous_end)
环比变化 = calc_growth_rate(current, previous)
```

输出示例：

```text
环比分析（销售员：张伟）：

当前周期（2026-04-01 至 2026-06-30）：¥120,000
对比周期（2026-01-01 至 2026-03-31）：¥210,000
环比变化：下降 42.86%（差额 ¥90,000）
```

`yoy` 销售员维度：

```text
今年指定周期销售额 = query_total_amount_by_rep(rep_id, current_start, current_end)
去年同期销售额 = query_total_amount_by_rep(rep_id, previous_year_start, previous_year_end)
```

`monthly` 销售员维度：

```text
月度销售趋势（近 6 个月，销售员：张伟）：

2026-01：¥80,000 订单数：4
2026-02：¥70,000 订单数：3 (↓12.50%)
...
```

## 权限与边界

- 趋势工具仍只能调用 Service 层，不直接访问 Repository。
- 销售员角色传入其它销售员姓名时，不返回该销售员是否真实存在的敏感细节，只返回不可访问/无数据类稳定提示。
- 主管角色传入其它大区销售员时，不能返回该销售员数据。
- 总监角色不受大区限制。
- `rep_name` 与 `region_name` 同时存在且不匹配时，应返回空数据或销售员不可访问提示，而不是自动忽略其中一个条件。

## 测试计划

### `tests/integration/test_sales_tools.py`

新增或扩展趋势工具测试：

- `mom` 支持指定 `rep_name`，返回销售员名称、当前周期、对比周期和环比变化。
- `monthly` 支持指定 `rep_name`，只返回该销售员月度数据。
- 不存在的 `rep_name` 返回稳定未知实体提示。

### `tests/integration/test_data_permissions.py`

增加权限场景：

- 销售员调用趋势工具查询自己时可以返回个人趋势。
- 销售员调用趋势工具查询其他销售员时不能看到数据。
- 主管调用趋势工具查询本大区销售员时可以看到数据。
- 主管调用趋势工具查询其它大区销售员时不能看到数据。

### 可选 Agent 测试

如需验证 Agent 规划，可在 `tests/integration/test_agent_memory.py` 或新增测试中使用 fake agent/tool-call 场景，确认“本季度掉量最大的销售员”类问题可以包含 `analyze_sales_trend` 工具调用。但本 spec 的最低验收以工具和 Service 行为为准。

## 验收标准

- `analyze_sales_trend` schema 中包含 `rep_name` 参数。
- `mom`、`yoy`、`monthly` 在传入 `rep_name` 时都能按销售员维度返回结果。
- 销售员维度趋势结果继续受当前用户权限上下文限制。
- 现有大区和全公司趋势调用保持兼容。
- `months` 默认值不变。
- 相关集成测试通过：

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/integration/test_sales_tools.py tests/integration/test_data_permissions.py -v
```

