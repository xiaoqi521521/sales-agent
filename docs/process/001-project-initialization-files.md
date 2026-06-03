# 项目初始化文件说明

本文档说明第一阶段项目初始化时创建或调整的文件，以及它们在 FastAPI 智能销售 Agent 项目中的职责。

## 根目录文件

### `.gitignore`

忽略本地环境和运行缓存文件，包括 `.env`、`.venv/`、`.pytest_cache/`、`__pycache__/`、Python 字节码文件、本地 SQLite 数据库文件等。作用是保持仓库干净，避免把本地配置、虚拟环境和运行产物提交进项目。

### `main.py`

保留为兼容入口，只从 `app.main` 导出 `app`。后续实际应用入口统一使用 `app.main:app`，但如果外部工具仍引用根目录 `main.py`，也能正常拿到 FastAPI 实例。

### `pyproject.toml`

项目配置和依赖声明文件。当前通过 `uv add` 引入了 FastAPI 项目初始化所需依赖，包括 `uvicorn[standard]`、`pydantic-settings`、`python-dotenv`、`sqlalchemy[asyncio]`、`aiosqlite`、`alembic`，以及开发依赖 `pytest`、`pytest-asyncio`、`httpx`。

### `uv.lock`

`uv` 自动生成和维护的依赖锁定文件。它记录当前环境解析出的精确包版本，保证之后在其他机器或后续开发中可以复现一致的依赖环境。

## 应用入口

### `app/__init__.py`

声明 `app` 是一个 Python 包。没有业务逻辑，只用于让 Python 能通过 `import app` 识别应用包。

### `app/main.py`

FastAPI 应用的正式启动入口。当前负责创建 `FastAPI` 实例、读取配置、注册 CORS 中间件，并将 API v1 路由挂载到配置中的前缀，默认是 `/api/v1`。

后续新增接口时，不直接堆到这里，而是继续放到 `app/api/v1/endpoints/`，再通过路由聚合进来。

## API 层

### `app/api/__init__.py`

声明 API 目录为 Python 包。当前无业务逻辑。

### `app/api/dependencies.py`

预留共享依赖位置。后续会放 FastAPI 的 `Depends` 依赖，例如数据库 session、当前登录用户、权限上下文等。

### `app/api/v1/__init__.py`

声明 v1 API 目录为 Python 包。用于组织版本化接口。

### `app/api/v1/router.py`

API v1 的路由聚合器。当前只挂载健康检查路由；后续会继续挂载 `auth`、`agent`、`sales` 等 endpoint 模块。

### `app/api/v1/endpoints/__init__.py`

声明 endpoints 目录为 Python 包。所有具体接口模块会放在这个目录下。

### `app/api/v1/endpoints/health.py`

健康检查接口模块。当前提供 `GET /api/v1/health`，返回应用名、版本号和运行状态。它用于验证应用是否可以启动、路由是否正确挂载，也是后续部署和测试的基础探针。

## Core 基础设施

### `app/core/__init__.py`

声明 core 目录为 Python 包。core 目录用于放项目基础设施代码。

### `app/core/config.py`

应用配置模块。使用 `pydantic-settings` 定义 `Settings`，支持从 `.env` 读取配置。当前包含应用名、版本号、API 前缀、数据库连接地址、SQL echo 开关和 CORS 来源配置。

`get_settings()` 使用缓存，避免每次依赖注入或模块调用时重复解析配置。

### `app/core/database.py`

数据库连接基础设施。当前基于 SQLAlchemy Async 创建异步 engine、异步 session factory，并提供 `get_db_session()` 依赖生成器。

后续 Repository 和 Service 层会通过这个 session 访问数据库，API 层也会通过 FastAPI 依赖注入获得 session。

## 数据模型

### `app/models/__init__.py`

统一导出当前核心模型：`Base`、`SalesRegion`、`SalesRep`、`Product`、`SalesOrder`。这样后续需要一次性导入模型元数据时更方便。

### `app/models/base.py`

定义 SQLAlchemy 声明式基类 `Base`。所有数据库模型都继承它，测试和迁移工具也会通过 `Base.metadata` 创建或管理表结构。

### `app/models/sales_region.py`

销售大区模型，对应 `sa_sales_region` 表。当前包含 `id`、`name`、`parent_region_id`、`created_at` 字段，并与销售员、订单建立关系。

后续权限隔离中，销售主管只能查看本大区数据，会依赖这个模型。

### `app/models/sales_rep.py`

销售员模型，对应 `sa_sales_rep` 表。当前包含 `id`、`name`、`region_id`、`role`、`email`、`created_at` 字段，并关联所属大区和订单。

后续销售员排名、个人数据权限过滤、异常预警都会使用它。

### `app/models/product.py`

产品模型，对应 `sa_product` 表。当前包含 `id`、`sku_code`、`name`、`category`、`unit_price`、`cost`、`status`、`created_at` 字段，并关联订单。

后续产品排名、品类占比、图表数据生成会使用它。

### `app/models/sales_order.py`

销售订单模型，对应 `sa_sales_order` 表。当前包含订单号、销售员、产品、大区、客户名、数量、单价、成交金额、成本、毛利、状态、订单日期和创建时间等字段。

它是销售分析的核心事实表。当前已定义日期、大区日期、销售员日期索引，用于后续按时间范围、区域、人员查询和统计。

## 数据库辅助文件

### `app/db/__init__.py`

声明 db 目录为 Python 包。该目录用于放数据库辅助脚本、结构文件和测试数据初始化逻辑。

### `app/db/schema.sql`

数据库结构 SQL 文件。当前包含四张核心业务表：`sa_sales_region`、`sa_sales_rep`、`sa_product`、`sa_sales_order`，以及销售员、产品、大区、订单日期、状态索引。

它主要用于人工查看表结构、和参考文献中的数据库设计做对照。应用运行和测试当前以 SQLAlchemy 模型为准。

### `app/db/data.sql`

完整测试数据 SQL 文件，是当前测试数据的唯一权威来源。MySQL 初始化时直接执行该文件，不再通过 Python seed 脚本中转。

这些数据覆盖 4 个大区、13 个销售员、20 个产品和 69 条订单，包含华北区近 14 天无订单、SKU-8821 近 14 天无销售、张磊近 60 天仅 1 单、王芳多笔退款等异常点，为后续明细查询、统计排名、趋势分析、图表生成和异常预警打基础。

## 测试文件

### `tests/integration/test_health.py`

健康检查集成测试。使用 `httpx.ASGITransport` 直接请求 FastAPI 应用，验证 `/api/v1/health` 返回预期状态。

该测试保证应用入口、路由聚合和配置读取是可用的。

### `tests/integration/test_database_sql.py`

数据库 SQL 数据文件测试。它不连接数据库，而是检查 `app/db/data.sql` 是否包含参考文献要求的数据规模和异常预埋点。

该测试保证测试数据文件没有被误删、漏改或替换成不完整数据。真实 MySQL 导入通过直接执行 `schema.sql` 和 `data.sql` 完成。

## 当前验证命令

### 运行基础测试

```bash
uv run python -m pytest tests\integration\test_health.py tests\integration\test_database_sql.py -v
```

当前验证结果为 2 个测试通过。

### 启动应用

```bash
uv run uvicorn app.main:app --reload
```

启动后访问：

```text
GET http://127.0.0.1:8000/api/v1/health
```

预期返回：

```json
{"name":"sales-agent","version":"0.1.0","status":"ok"}
```

## 后续扩展位置

- 新增 API：放到 `app/api/v1/endpoints/`，并在 `app/api/v1/router.py` 挂载。
- 新增配置：放到 `app/core/config.py`。
- 新增数据库连接能力：放到 `app/core/database.py`。
- 新增表结构：放到 `app/models/`，必要时同步更新 `app/db/schema.sql`。
- 新增初始化数据：放到 `app/db/data.sql`，MySQL 初始化时直接执行该 SQL 文件。
- 新增业务查询：后续放到 `app/repositories/` 和 `app/services/`。
- 新增 Agent 工具：后续放到 `app/tools/`。
- 新增 Agent 编排：后续放到 `app/agent/`。
