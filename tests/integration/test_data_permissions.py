from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth_context import CurrentUser
from app.core.user_context import reset_current_user, set_current_user
from app.models.base import Base
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep
from app.services.sales_query_service import SalesQueryService
from app.tools.registry import create_sales_tools


@pytest.mark.asyncio
async def test_sales_rep_can_only_see_own_orders_and_ranking():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        service = SalesQueryService()
        user_token = set_current_user(
            CurrentUser(
                username="Zhang Wei",
                role="SALES_REP",
                region_id=1,
                rep_id=2,
            )
        )
        try:
            start = date(2026, 1, 1)
            end = date(2026, 1, 31)

            orders = await service.query_orders(session, rep_id=None, region_id=None, start=start, end=end)
            assert [order.order_no for order in orders] == ["ORD-EAST-ZHANG"]

            ranking = await service.query_rep_ranking(session, start, end, top_n=10)
            assert [row.rep_id for row in ranking] == [2]

            regions = await service.query_region_ranking(session, start, end)
            assert [row.region_id for row in regions] == [1]
            assert regions[0].total_amount == Decimal("1000.00")
        finally:
            reset_current_user(user_token)

    await engine.dispose()


@pytest.mark.asyncio
async def test_sales_manager_can_only_see_own_region():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        service = SalesQueryService()
        user_token = set_current_user(
            CurrentUser(
                username="East Manager",
                role="SALES_MANAGER",
                region_id=1,
                rep_id=1,
            )
        )
        try:
            start = date(2026, 1, 1)
            end = date(2026, 1, 31)

            orders = await service.query_orders(session, rep_id=None, region_id=None, start=start, end=end)
            assert [order.order_no for order in orders] == ["ORD-EAST-ZHANG", "ORD-EAST-WANG"]

            north_orders = await service.query_orders(session, rep_id=None, region_id=2, start=start, end=end)
            assert north_orders == []

            regions = await service.query_region_ranking(session, start, end)
            assert [row.region_id for row in regions] == [1]
        finally:
            reset_current_user(user_token)

    await engine.dispose()


@pytest.mark.asyncio
async def test_sales_director_can_see_all_company_data():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        service = SalesQueryService()
        user_token = set_current_user(
            CurrentUser(
                username="Director",
                role="SALES_DIRECTOR",
                region_id=None,
                rep_id=5,
            )
        )
        try:
            start = date(2026, 1, 1)
            end = date(2026, 1, 31)

            orders = await service.query_orders(session, rep_id=None, region_id=None, start=start, end=end)
            assert [order.order_no for order in orders] == ["ORD-EAST-ZHANG", "ORD-EAST-WANG", "ORD-NORTH-ZHANG"]

            regions = await service.query_region_ranking(session, start, end)
            assert [row.region_id for row in regions] == [2, 1]
        finally:
            reset_current_user(user_token)

    await engine.dispose()


@pytest.mark.asyncio
async def test_sales_tools_apply_current_user_permission_scope():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        user_token = set_current_user(
            CurrentUser(
                username="East Manager",
                role="SALES_MANAGER",
                region_id=1,
                rep_id=1,
            )
        )
        tools = {tool.name: tool for tool in create_sales_tools(session=session)}

        try:
            text = await tools["query_sales_orders"].ainvoke(
                {
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "region_name": "华北区",
                    "rep_name": "",
                    "customer_name": "",
                    "limit": 10,
                }
            )
        finally:
            reset_current_user(user_token)

        assert "ORD-NORTH-ZHANG" not in text
        assert "ORD-EAST-ZHANG" not in text

    await engine.dispose()


@pytest.mark.asyncio
async def test_sales_rep_summary_tool_rejects_team_and_region_rankings():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        user_token = set_current_user(
            CurrentUser(
                username="Zhang Wei",
                role="SALES_REP",
                region_id=1,
                rep_id=2,
            )
        )
        tools = {tool.name: tool for tool in create_sales_tools(session=session)}

        try:
            rep_ranking = await tools["calculate_sales_summary"].ainvoke(
                {
                    "summary_type": "rep_ranking",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "region_name": "",
                    "top_n": 5,
                }
            )
            region_ranking = await tools["calculate_sales_summary"].ainvoke(
                {
                    "summary_type": "region_ranking",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "region_name": "",
                    "top_n": 5,
                }
            )
            product_ranking = await tools["calculate_sales_summary"].ainvoke(
                {
                    "summary_type": "product_ranking",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "region_name": "",
                    "top_n": 5,
                }
            )
        finally:
            reset_current_user(user_token)

        assert "NO_PERMISSION_REP_RANKING" in rep_ranking
        assert "NO_PERMISSION_REGION_RANKING" in region_ranking
        assert "PERSONAL_PRODUCT_RANKING" in product_ranking
        assert "ORD-EAST-WANG" not in product_ranking

    await engine.dispose()


@pytest.mark.asyncio
async def test_sales_trend_tool_applies_rep_permission_scope():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        rep_token = set_current_user(
            CurrentUser(
                username="Zhang Wei",
                role="SALES_REP",
                region_id=1,
                rep_id=2,
            )
        )
        tools = {tool.name: tool for tool in create_sales_tools(session=session, today=date(2026, 1, 31))}

        try:
            own_trend = await tools["analyze_sales_trend"].ainvoke(
                {
                    "trend_type": "mom",
                    "current_start": "2026-01-01",
                    "current_end": "2026-01-31",
                    "previous_start": "2025-12-01",
                    "previous_end": "2025-12-31",
                    "region_name": "",
                    "rep_name": "Zhang Wei",
                    "months": 2,
                }
            )
            other_trend = await tools["analyze_sales_trend"].ainvoke(
                {
                    "trend_type": "mom",
                    "current_start": "2026-01-01",
                    "current_end": "2026-01-31",
                    "previous_start": "2025-12-01",
                    "previous_end": "2025-12-31",
                    "region_name": "",
                    "rep_name": "Wang Fang",
                    "months": 2,
                }
            )
        finally:
            reset_current_user(rep_token)

        assert "环比分析（销售员：Zhang Wei）" in own_trend
        assert "当前周期（2026-01-01 至 2026-01-31）：¥1,000" in own_trend
        assert other_trend.startswith("TOOL_UNKNOWN_ENTITY")
        assert "Wang Fang" in other_trend

    await engine.dispose()


@pytest.mark.asyncio
async def test_sales_manager_can_query_trend_for_own_region_rep_only():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        manager_token = set_current_user(
            CurrentUser(
                username="East Manager",
                role="SALES_MANAGER",
                region_id=1,
                rep_id=1,
            )
        )
        tools = {tool.name: tool for tool in create_sales_tools(session=session, today=date(2026, 1, 31))}

        try:
            own_region_trend = await tools["analyze_sales_trend"].ainvoke(
                {
                    "trend_type": "mom",
                    "current_start": "2026-01-01",
                    "current_end": "2026-01-31",
                    "previous_start": "2025-12-01",
                    "previous_end": "2025-12-31",
                    "region_name": "",
                    "rep_name": "Wang Fang",
                    "months": 2,
                }
            )
            other_region_trend = await tools["analyze_sales_trend"].ainvoke(
                {
                    "trend_type": "mom",
                    "current_start": "2026-01-01",
                    "current_end": "2026-01-31",
                    "previous_start": "2025-12-01",
                    "previous_end": "2025-12-31",
                    "region_name": "",
                    "rep_name": "Zhang Lei",
                    "months": 2,
                }
            )
        finally:
            reset_current_user(manager_token)

        assert "环比分析（销售员：Wang Fang）" in own_region_trend
        assert "当前周期（2026-01-01 至 2026-01-31）：¥1,500" in own_region_trend
        assert other_region_trend.startswith("TOOL_UNKNOWN_ENTITY")
        assert "Zhang Lei" in other_region_trend

    await engine.dispose()


def _sample_rows():
    return [
        SalesRegion(id=1, name="华东区"),
        SalesRegion(id=2, name="华北区"),
        SalesRep(id=1, name="East Manager", region_id=1, role="SALES_MANAGER", email="manager@example.com"),
        SalesRep(id=2, name="Zhang Wei", region_id=1, role="SALES_REP", email="zhangwei@example.com"),
        SalesRep(id=3, name="Wang Fang", region_id=1, role="SALES_REP", email="wangfang@example.com"),
        SalesRep(id=4, name="Zhang Lei", region_id=2, role="SALES_REP", email="zhanglei@example.com"),
        SalesRep(id=5, name="Director", region_id=0, role="SALES_DIRECTOR", email="director@example.com"),
        Product(
            id=1,
            sku_code="SKU-1001",
            name="Laptop",
            category="Digital",
            unit_price=Decimal("500.00"),
            cost=Decimal("300.00"),
            status="ACTIVE",
        ),
        SalesOrder(
            id=1,
            order_no="ORD-EAST-ZHANG",
            rep_id=2,
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
            order_no="ORD-EAST-WANG",
            rep_id=3,
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
            order_no="ORD-NORTH-ZHANG",
            rep_id=4,
            product_id=1,
            region_id=2,
            customer_name="Beijing Tech",
            quantity=6,
            unit_price=Decimal("500.00"),
            amount=Decimal("3000.00"),
            cost=Decimal("1800.00"),
            profit=Decimal("1200.00"),
            status="COMPLETED",
            order_date=date(2026, 1, 20),
        ),
    ]
