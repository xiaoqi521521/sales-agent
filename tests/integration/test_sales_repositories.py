from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest

from app.models.base import Base
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep
from app.repositories.product_repository import ProductRepository
from app.repositories.sales_order_repository import SalesOrderRepository
from app.repositories.sales_region_repository import SalesRegionRepository
from app.repositories.sales_rep_repository import SalesRepRepository


@pytest.mark.asyncio
async def test_reference_repositories_query_core_entities():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        region_repo = SalesRegionRepository()
        rep_repo = SalesRepRepository()
        product_repo = ProductRepository()

        assert (await region_repo.find_by_name(session, "华东区")).id == 1
        assert [rep.name for rep in await rep_repo.find_by_region_id(session, 1)] == ["张伟", "王芳"]
        assert [rep.name for rep in await rep_repo.find_by_role(session, "SALES_REP")] == ["张伟", "王芳"]
        assert (await rep_repo.find_by_name(session, "张伟")).id == 2
        assert (await product_repo.find_by_sku_code(session, "SKU-1001")).name == "华为 Mate 70 Pro 手机"
        assert [p.sku_code for p in await product_repo.find_by_category(session, "数码产品")] == [
            "SKU-1001",
            "SKU-1002",
        ]
        assert [p.sku_code for p in await product_repo.find_by_status(session, "ACTIVE")] == [
            "SKU-1001",
            "SKU-1002",
        ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_sales_order_repository_matches_reference_queries():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        repo = SalesOrderRepository()
        start = date(2026, 1, 1)
        end = date(2026, 1, 31)

        assert [o.order_no for o in await repo.find_by_rep_id_and_order_date_between(session, 2, start, end)] == [
            "ORD-001",
            "ORD-002",
        ]
        assert [o.order_no for o in await repo.find_by_region_id_and_order_date_between(session, 1, start, end)] == [
            "ORD-001",
            "ORD-002",
            "ORD-003",
        ]
        assert [o.order_no for o in await repo.find_by_product_id_and_order_date_between(session, 1, start, end)] == [
            "ORD-001",
            "ORD-003",
        ]
        assert await repo.sum_amount_by_region(session, 1, start, end) == Decimal("2500.00")
        assert await repo.sum_amount_by_rep(session, 2, start, end) == Decimal("1000.00")
        assert await repo.find_last_order_date_by_product(session, 1) == date(2026, 1, 15)
        assert await repo.count_completed_by_region(session, 1, start, end) == 2

        rep_ranking = await repo.find_rep_ranking(session, start, end)
        assert rep_ranking[0] == (3, Decimal("1500.00"))

        region_ranking = await repo.find_region_ranking(session, start, end)
        assert region_ranking == [(1, Decimal("2500.00"))]

        product_ranking = await repo.find_product_ranking(session, start, end)
        assert product_ranking[0] == (1, Decimal("2500.00"), 3)

        monthly_trend = await repo.find_monthly_trend(session, 1, start, end)
        assert monthly_trend == [("2026-01", Decimal("2500.00"), 2)]

        refund_rates = await repo.find_refund_rate_by_rep(session, start, end)
        assert refund_rates == [(2, 1, 2), (3, 0, 1)]

    await engine.dispose()


def _sample_rows():
    return [
        SalesRegion(id=1, name="华东区"),
        SalesRep(id=2, name="张伟", region_id=1, role="SALES_REP", email="zhangwei@jichi.com"),
        SalesRep(id=3, name="王芳", region_id=1, role="SALES_REP", email="wangfang@jichi.com"),
        Product(
            id=1,
            sku_code="SKU-1001",
            name="华为 Mate 70 Pro 手机",
            category="数码产品",
            unit_price=Decimal("6999.00"),
            cost=Decimal("4200.00"),
            status="ACTIVE",
        ),
        Product(
            id=2,
            sku_code="SKU-1002",
            name="苹果 iPhone 16 手机",
            category="数码产品",
            unit_price=Decimal("7999.00"),
            cost=Decimal("5100.00"),
            status="ACTIVE",
        ),
        SalesOrder(
            id=1,
            order_no="ORD-001",
            rep_id=2,
            product_id=1,
            region_id=1,
            customer_name="上海某科技公司",
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
            product_id=2,
            region_id=1,
            customer_name="南京运动装备店",
            quantity=1,
            unit_price=Decimal("200.00"),
            amount=Decimal("200.00"),
            cost=Decimal("100.00"),
            profit=Decimal("100.00"),
            status="REFUNDED",
            order_date=date(2026, 1, 12),
        ),
        SalesOrder(
            id=3,
            order_no="ORD-003",
            rep_id=3,
            product_id=1,
            region_id=1,
            customer_name="杭州旗舰门店",
            quantity=1,
            unit_price=Decimal("1500.00"),
            amount=Decimal("1500.00"),
            cost=Decimal("900.00"),
            profit=Decimal("600.00"),
            status="COMPLETED",
            order_date=date(2026, 1, 15),
        ),
    ]
