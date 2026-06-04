# Service 层与 Schemas 编写过程

本文档记录销售查询 Service 层和 Pydantic schemas 的编写过程，便于后续继续开发工具层、Agent 层和 API 层时理解当前设计。

## 参考资料

本阶段先读取 `docs/reference/00_SUMMARY.md`，再按需加载：

- `docs/reference/08_service查询封装层.md`
- `docs/reference/DTO/OrderSummaryDTO.java`
- `docs/reference/DTO/RepSalesDTO.java`
- `docs/reference/DTO/RegionSalesDTO.java`
- `docs/reference/DTO/ProductSalesDTO.java`
- `docs/reference/DTO/MonthlyTrendDTO.java`
- `docs/reference/DTO/AnomalyDTO.java`

参考文献的核心要求是：工具层不能直接访问 Repository，应统一通过 `SalesQueryService` 获取销售数据；返回给上层的数据应使用 DTO，而不是直接暴露 ORM Entity。

## 编写顺序

1. 先确认当前已有 Repository 能力

   已有 Repository 提供了订单明细查询、总销售额汇总、销售员/大区/产品排名、月度趋势、产品最近出单日期、退单率统计和大区完成订单数统计。

2. 先写测试

   新增 `tests/integration/test_sales_query_service.py`，使用 `sqlite+aiosqlite:///:memory:` 创建临时内存数据库，插入少量样例数据，验证 Service 返回 DTO，而不是 ORM 对象。

   SQLite 内存库只用于测试，不是业务运行时数据源。真实业务数据源仍然是 MySQL。

3. 创建 schemas

   新增 `app/schemas/sales.py`，用 Pydantic 对齐参考项目 DTO：

   - `OrderSummaryDTO`
   - `RepSalesDTO`
   - `RegionSalesDTO`
   - `ProductSalesDTO`
   - `MonthlyTrendDTO`
   - `AnomalyDTO`
   - `OrderQueryParams`

   Python 内部使用 `snake_case` 字段，例如 `order_no`；通过 Pydantic alias 支持输出 Java DTO 风格字段，例如 `orderNo`。

4. 创建 Service

   新增 `app/services/sales_query_service.py`，封装销售查询业务逻辑。Service 内部组合 Repository 查询结果，并补齐名称解析、排名结果 DTO 转换、增长率计算等逻辑。

5. 导出包入口

   新增 `app/schemas/__init__.py` 和 `app/services/__init__.py`，便于后续统一导入。

## 主要文件职责

### `app/schemas/sales.py`

定义销售分析相关 DTO 和查询参数对象。它是 Service 层、工具层、API 层之间传输结构化数据的边界。

特别注意：

- 金额字段使用 `Decimal`。
- 日期字段使用 `date`。
- DTO 字段语义对齐 `docs/reference/DTO` 下 Java record。
- `AnomalyDTO` 虽然本阶段 Service 不直接使用，但提前放入 schemas，供异常检测工具复用。

### `app/services/sales_query_service.py`

统一销售查询服务，是工具层访问销售数据的唯一入口。当前提供：

- `query_orders`
- `query_total_amount`
- `query_rep_ranking`
- `query_region_ranking`
- `query_product_ranking`
- `query_monthly_trend`
- `calc_growth_rate`
- `query_last_order_date`
- `query_order_count`
- `query_refund_rates`
- `get_rep_name`
- `get_region_name`
- `get_region_id_by_name`
- `get_rep_id_by_name`

## 设计取舍

- Service 返回 DTO，不直接返回 ORM Entity。
- Repository 只负责数据库访问，不写工具描述、权限、缓存和 Agent 逻辑。
- Service 做名称补全和 ID 解析，让工具层可以使用用户自然语言里的大区名、销售员名。
- 当前没有引入权限过滤；后续认证阶段会在 Service 查询条件中注入权限上下文。
- 当前没有单独创建 `chart_service.py` 或 `anomaly_service.py`，因为 Phase 4 先按参考工具粒度直接复用 `SalesQueryService`。

## 验证命令

```bash
uv run python -m pytest tests\integration\test_sales_query_service.py -v
```

完成后与其他集成测试一起验证：

```bash
uv run python -m pytest tests\integration -v
```

当时验证结果为 `11 passed`，后续工具层完成后完整集成测试扩展为 `14 passed`。
