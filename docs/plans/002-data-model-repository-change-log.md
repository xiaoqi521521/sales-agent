# 数据模型与 Repository 层改动记录

> 对应提交：`c1206d4 feat: align sales data models and repositories`

## 背景

本次改动基于 `docs/reference/04_数据库设计.md`、`docs/reference/05_测试数据初始化.md`、`docs/reference/07_entity与repository层.md` 和 `docs/reference/08_service查询封装层.md`，目标是让项目的数据表、SQLAlchemy 模型、测试数据和 Repository 层与参考项目保持一致。

## 已完成改动

1. 数据库初始化方式调整

- 新增 `app/db/data.sql`，作为测试数据的唯一 SQL 来源。
- 保留并修正 `app/db/schema.sql`，用于创建 MySQL 业务表。
- 删除 `app/db/seed.py`，不再通过 Python seed 脚本绕一层导入数据。
- 删除旧的 `tests/integration/test_database_seed.py`。

2. MySQL 表结构对齐

当前业务库使用四张核心表：

- `sa_sales_region`
- `sa_sales_rep`
- `sa_product`
- `sa_sales_order`

字段、类型、默认值、唯一键和普通索引已按参考 DDL 对齐。ORM 模型不额外声明数据库外键约束，因为参考 DDL 中只定义普通字段和索引。

3. SQLAlchemy 模型重构

更新 `app/models/` 下四个实体类：

- `SalesRegion`
- `SalesRep`
- `Product`
- `SalesOrder`

主要变化：

- 表名从旧的简化命名改为 `sa_*` 命名。
- 字段补齐为参考 DDL 中的完整字段。
- 金额字段统一使用 `Decimal` / `Numeric`。
- 时间字段补齐 `created_at`。
- 移除与参考 DDL 不一致的 ORM `ForeignKey` 和 `relationship`。

4. Repository 层创建

新增 `app/repositories/`：

- `base_repository.py`
- `sales_region_repository.py`
- `sales_rep_repository.py`
- `product_repository.py`
- `sales_order_repository.py`
- `__init__.py`

Repository 层提供：

- 通用 `find_by_id`、`find_all`。
- 大区按名称查询。
- 销售员按大区、角色、姓名查询。
- 产品按 SKU、品类、状态查询。
- 订单按销售员、大区、产品和日期范围查询。
- 销售额汇总、销售员排名、大区排名、产品排名。
- 月度趋势、最近出单日期、退单统计、指定大区完成订单数。

5. 测试补充

新增测试：

- `tests/integration/test_database_sql.py`
- `tests/integration/test_model_mapping.py`
- `tests/integration/test_sales_repositories.py`

覆盖内容：

- `data.sql` 测试数据完整性。
- 关键异常测试数据点。
- SQLAlchemy 模型与 MySQL DDL 的字段映射。
- Repository 查询行为。

6. 依赖调整

通过 `uv` 引入 MySQL 异步驱动：

- `asyncmy`

相关文件：

- `pyproject.toml`
- `uv.lock`

## 验证结果

已执行：

```bash
uv run python -m pytest tests\integration -v
```

结果：

```text
9 passed
```

已额外通过 MySQL `information_schema` 核对真实数据库表结构，四张表的字段、类型、唯一键和普通索引与参考 DDL 对齐。

## 后续建议

下一步可以进入 Service 层：

- 创建 `app/schemas/sales.py` 中的 DTO / 查询条件对象。
- 创建 `app/services/sales_query_service.py`。
- 将工具层未来需要的查询入口统一封装到 Service 层。
- Repository 层继续保持只负责数据库访问，不写权限、缓存和 Agent 业务逻辑。
