# 销售趋势工具支持销售员维度改造过程

## 背景

用户问题“本季度掉量最大的销售员是谁，分析一下原因”需要 Agent 能对销售员做周期对比。原有 `analyze_sales_trend` 只支持全公司或大区维度：

- `mom`：按全公司/大区计算环比。
- `yoy`：按全公司/大区计算同比。
- `monthly`：按全公司/大区返回近 N 个月趋势。

因此 Agent 即使能通过销售员排行和订单明细推断掉量，也无法调用趋势工具对指定销售员做标准化趋势分析。本次改造基于 `docs/specs/project/006-sales-trend-tool-rep-dimension.md`，只增强销售员维度，不调整 `months` 默认值。

## 测试先行

先新增失败测试，再实现代码。

新增和扩展测试：

- `tests/integration/test_sales_tools.py`
  - 在趋势工具测试中增加 `rep_name="Zhang Lei"` 的 `mom` 环比断言。
  - 增加 `rep_name="Zhang Lei"` 的 `monthly` 月度趋势断言。
  - 增加不存在销售员 `rep_name="Nobody"` 的稳定未知实体提示断言。
- `tests/integration/test_data_permissions.py`
  - 验证销售员可以查询自己的趋势，不能查询其他销售员趋势。
  - 验证主管可以查询本大区销售员趋势，不能查询其它大区销售员趋势。

红灯验证命令：

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/integration/test_sales_tools.py::test_trend_chart_and_anomaly_tools_match_reference_outputs tests/integration/test_sales_tools.py::test_sales_tools_return_stable_boundary_messages tests/integration/test_data_permissions.py::test_sales_trend_tool_applies_rep_permission_scope tests/integration/test_data_permissions.py::test_sales_manager_can_query_trend_for_own_region_rep_only -v
```

红灯结果：

```text
4 failed
```

失败原因符合预期：`rep_name` 参数尚未被 schema 和工具函数接收，趋势工具忽略销售员参数，仍返回“全公司”趋势。

## 主要代码改动

### `app/tools/schemas.py`

在 `SalesTrendInput` 中新增：

```python
rep_name: str | None = Field(default=None, description="销售员姓名；空字符串或 null 表示不限销售员")
```

该参数复用工具输入模型的普通字符串处理方式，不改变日期校验和 `months` 默认值。

### `app/services/sales_query_service.py`

新增 Service 层封装，避免趋势工具直接访问 Repository：

```python
async def query_total_amount_by_rep(...)
async def query_monthly_trend_by_rep(...)
```

这两个方法都先调用现有 `_order_scope(...)` 做权限收敛：

- 销售员只能查询自己。
- 主管只能查询本大区销售员。
- 总监可以查询任意销售员。
- 越权时返回 `Decimal("0")` 或空列表。

### `app/tools/sales_trend_tool.py`

调整 `analyze_sales_trend`：

- 函数签名增加 `rep_name`。
- 工具调用日志记录 `rep_name`。
- 新增 `TrendScope`，统一表达当前趋势查询范围：
  - `region_id`
  - `rep_id`
  - `label`
- 新增 `_resolve_scope(...)`：
  - 先解析 `region_name`。
  - 再通过 `service.get_rep_id_by_name(...)` 解析 `rep_name`。
  - 销售员不存在或不可见时返回 `TOOL_UNKNOWN_ENTITY`。
  - `region_name` 与 `rep_name` 同时存在时，要求销售员在该大区范围内可见。
- `mom` / `yoy` 通过 `_query_total_amount(...)` 自动选择大区/全公司汇总或销售员汇总。
- `monthly` 在有 `rep_id` 时调用 `service.query_monthly_trend_by_rep(...)`，否则保持原有全公司/大区逻辑。

## 权限边界

本次没有把权限判断放进 Prompt，也没有让工具绕过 Service。

权限链路保持为：

```text
FastAPI protected dependency
-> contextvars current user
-> SalesQueryService
-> _order_scope(...)
-> repository query
```

因此即使 Agent 或用户传入其它销售员姓名，Service 仍会按当前用户权限过滤。

## 验证

目标红灯测试转绿：

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/integration/test_sales_tools.py::test_trend_chart_and_anomaly_tools_match_reference_outputs tests/integration/test_sales_tools.py::test_sales_tools_return_stable_boundary_messages tests/integration/test_data_permissions.py::test_sales_trend_tool_applies_rep_permission_scope tests/integration/test_data_permissions.py::test_sales_manager_can_query_trend_for_own_region_rep_only -v
```

结果：

```text
4 passed
```

按 spec 验收命令运行：

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/integration/test_sales_tools.py tests/integration/test_data_permissions.py -v
```

结果：

```text
12 passed
```

## 当前行为示例

销售员维度环比：

```text
环比分析（销售员：Zhang Lei）：

当前周期（2026-01-01 至 2026-01-31）：¥200
对比周期（2025-12-01 至 2025-12-31）：¥6,000
环比变化：下降 96.67%（差额 ¥5,800）
```

销售员维度月度趋势：

```text
月度销售趋势（近 3 个月，销售员：Zhang Lei）：

2025-12：¥6,000 订单数：3
2026-01：¥200 订单数：1 (↓96.67%)
2026-02：¥500 订单数：1 (↑150.00%)
```

