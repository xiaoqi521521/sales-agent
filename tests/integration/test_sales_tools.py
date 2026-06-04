import json
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest

from app.models.base import Base
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep
from app.tools.registry import create_sales_tools


@pytest.mark.asyncio
async def test_sales_tools_are_registered_with_reference_granularity():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        tools = create_sales_tools(session=session, today=date(2026, 2, 15))

        assert [tool.name for tool in tools] == [
            "query_sales_orders",
            "calculate_sales_summary",
            "analyze_sales_trend",
            "generate_sales_chart",
            "detect_sales_anomalies",
        ]
        assert all(tool.description for tool in tools)

    await engine.dispose()


@pytest.mark.asyncio
async def test_query_and_summary_tools_return_readable_sales_text():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        tools = {tool.name: tool for tool in create_sales_tools(session=session, today=date(2026, 2, 15))}

        orders_text = await tools["query_sales_orders"].ainvoke(
            {
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "region_name": "East",
                "rep_name": "Zhang Wei",
                "limit": 10,
            }
        )
        assert "订单查询结果" in orders_text
        assert "ORD-001" in orders_text
        assert "Zhang Wei" in orders_text
        assert "小计：完成订单 1 笔" in orders_text

        summary_text = await tools["calculate_sales_summary"].ainvoke(
            {
                "summary_type": "rep_ranking",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "region_name": "",
                "top_n": 2,
            }
        )
        assert "销售员业绩排名" in summary_text
        assert "第 1 名：Wang Fang" in summary_text

    await engine.dispose()


@pytest.mark.asyncio
async def test_trend_chart_and_anomaly_tools_match_reference_outputs():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        tools = {tool.name: tool for tool in create_sales_tools(session=session, today=date(2026, 2, 15))}

        trend_text = await tools["analyze_sales_trend"].ainvoke(
            {
                "trend_type": "mom",
                "current_start": "2026-01-01",
                "current_end": "2026-01-31",
                "previous_start": "2025-12-01",
                "previous_end": "2025-12-31",
                "region_name": "East",
                "months": 2,
            }
        )
        assert "环比分析" in trend_text
        assert "当前周期" in trend_text
        assert "对比周期" in trend_text

        chart_text = await tools["generate_sales_chart"].ainvoke(
            {
                "chart_type": "pie",
                "dimension": "region",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "months": 3,
                "region_name": "",
                "title": "Region Share",
            }
        )
        assert chart_text.startswith("CHART_JSON:")
        option = json.loads(chart_text.removeprefix("CHART_JSON:"))
        assert option["series"][0]["type"] == "pie"
        assert option["title"]["text"] == "Region Share"

        anomaly_text = await tools["detect_sales_anomalies"].ainvoke({})
        assert "异常检测结果" in anomaly_text
        assert "产品连续零销售" in anomaly_text
        assert "销售员退单率异常" in anomaly_text
        assert "销售员业绩骤降" in anomaly_text

    await engine.dispose()


def _sample_rows():
    return [
        SalesRegion(id=1, name="East"),
        SalesRegion(id=2, name="North"),
        SalesRep(id=1, name="Zhang Wei", region_id=1, role="SALES_REP", email="zhangwei@example.com"),
        SalesRep(id=2, name="Wang Fang", region_id=1, role="SALES_REP", email="wangfang@example.com"),
        SalesRep(id=3, name="Zhang Lei", region_id=2, role="SALES_REP", email="zhanglei@example.com"),
        Product(
            id=1,
            sku_code="SKU-1001",
            name="Laptop",
            category="Digital",
            unit_price=Decimal("500.00"),
            cost=Decimal("300.00"),
            status="ACTIVE",
        ),
        Product(
            id=2,
            sku_code="SKU-8821",
            name="Smart Watch Pro",
            category="Digital",
            unit_price=Decimal("200.00"),
            cost=Decimal("120.00"),
            status="ACTIVE",
        ),
        Product(
            id=3,
            sku_code="SKU-3001",
            name="Jacket",
            category="Clothing",
            unit_price=Decimal("300.00"),
            cost=Decimal("180.00"),
            status="ACTIVE",
        ),
        SalesOrder(
            id=1,
            order_no="ORD-001",
            rep_id=1,
            product_id=1,
            region_id=1,
            customer_name="Shanghai Tech",
            quantity=2,
            unit_price=Decimal("500.00"),
            amount=Decimal("1000.00"),
            cost=Decimal("600.00"),
            profit=Decimal("400.00"),
            status="COMPLETED",
            order_date=date(2026, 1, 10),
        ),
        SalesOrder(
            id=2,
            order_no="ORD-002",
            rep_id=2,
            product_id=1,
            region_id=1,
            customer_name="Hangzhou Flagship",
            quantity=3,
            unit_price=Decimal("500.00"),
            amount=Decimal("1500.00"),
            cost=Decimal("900.00"),
            profit=Decimal("600.00"),
            status="COMPLETED",
            order_date=date(2026, 1, 15),
        ),
        SalesOrder(
            id=3,
            order_no="ORD-003",
            rep_id=2,
            product_id=2,
            region_id=1,
            customer_name="Refund Customer A",
            quantity=1,
            unit_price=Decimal("200.00"),
            amount=Decimal("200.00"),
            cost=Decimal("120.00"),
            profit=Decimal("80.00"),
            status="REFUNDED",
            order_date=date(2026, 1, 20),
        ),
        SalesOrder(
            id=4,
            order_no="ORD-004",
            rep_id=2,
            product_id=2,
            region_id=1,
            customer_name="Refund Customer B",
            quantity=1,
            unit_price=Decimal("200.00"),
            amount=Decimal("200.00"),
            cost=Decimal("120.00"),
            profit=Decimal("80.00"),
            status="REFUNDED",
            order_date=date(2026, 1, 21),
        ),
        SalesOrder(
            id=5,
            order_no="ORD-005",
            rep_id=2,
            product_id=3,
            region_id=1,
            customer_name="Refund Customer C",
            quantity=1,
            unit_price=Decimal("300.00"),
            amount=Decimal("300.00"),
            cost=Decimal("180.00"),
            profit=Decimal("120.00"),
            status="REFUNDED",
            order_date=date(2026, 1, 22),
        ),
        SalesOrder(
            id=6,
            order_no="ORD-006",
            rep_id=3,
            product_id=1,
            region_id=2,
            customer_name="North Old A",
            quantity=4,
            unit_price=Decimal("500.00"),
            amount=Decimal("2000.00"),
            cost=Decimal("1200.00"),
            profit=Decimal("800.00"),
            status="COMPLETED",
            order_date=date(2025, 12, 5),
        ),
        SalesOrder(
            id=7,
            order_no="ORD-007",
            rep_id=3,
            product_id=1,
            region_id=2,
            customer_name="North Old B",
            quantity=4,
            unit_price=Decimal("500.00"),
            amount=Decimal("2000.00"),
            cost=Decimal("1200.00"),
            profit=Decimal("800.00"),
            status="COMPLETED",
            order_date=date(2025, 12, 12),
        ),
        SalesOrder(
            id=8,
            order_no="ORD-008",
            rep_id=3,
            product_id=1,
            region_id=2,
            customer_name="North Old C",
            quantity=4,
            unit_price=Decimal("500.00"),
            amount=Decimal("2000.00"),
            cost=Decimal("1200.00"),
            profit=Decimal("800.00"),
            status="COMPLETED",
            order_date=date(2025, 12, 20),
        ),
        SalesOrder(
            id=9,
            order_no="ORD-009",
            rep_id=3,
            product_id=2,
            region_id=2,
            customer_name="Smart Watch Buyer",
            quantity=1,
            unit_price=Decimal("200.00"),
            amount=Decimal("200.00"),
            cost=Decimal("120.00"),
            profit=Decimal("80.00"),
            status="COMPLETED",
            order_date=date(2026, 1, 1),
        ),
        SalesOrder(
            id=10,
            order_no="ORD-010",
            rep_id=3,
            product_id=1,
            region_id=2,
            customer_name="North Recent",
            quantity=1,
            unit_price=Decimal("500.00"),
            amount=Decimal("500.00"),
            cost=Decimal("300.00"),
            profit=Decimal("200.00"),
            status="COMPLETED",
            order_date=date(2026, 2, 5),
        ),
    ]
