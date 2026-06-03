from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest

from app.models.base import Base
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep
from app.schemas.sales import (
    AnomalyDTO,
    MonthlyTrendDTO,
    OrderSummaryDTO,
    ProductSalesDTO,
    RegionSalesDTO,
    RepSalesDTO,
)
from app.services.sales_query_service import SalesQueryService


@pytest.mark.asyncio
async def test_sales_query_service_returns_order_summaries_and_totals():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        service = SalesQueryService()
        start = date(2026, 1, 1)
        end = date(2026, 1, 31)

        orders = await service.query_orders(session, rep_id=2, region_id=None, start=start, end=end)
        assert orders == [
            OrderSummaryDTO(
                order_no="ORD-001",
                rep_name="Zhang Wei",
                customer_name="Shanghai Tech",
                amount=Decimal("1000.00"),
                status="COMPLETED",
                order_date=date(2026, 1, 10),
            ),
            OrderSummaryDTO(
                order_no="ORD-002",
                rep_name="Zhang Wei",
                customer_name="Nanjing Sports",
                amount=Decimal("200.00"),
                status="REFUNDED",
                order_date=date(2026, 1, 12),
            ),
        ]

        assert orders[0].model_dump(by_alias=True) == {
            "orderNo": "ORD-001",
            "repName": "Zhang Wei",
            "customerName": "Shanghai Tech",
            "amount": Decimal("1000.00"),
            "status": "COMPLETED",
            "orderDate": date(2026, 1, 10),
        }
        assert await service.query_total_amount(session, region_id=1, start=start, end=end) == Decimal("2500.00")
        assert await service.get_rep_name(session, 2) == "Zhang Wei"
        assert await service.get_region_name(session, 1) == "East"
        assert await service.get_region_id_by_name(session, "East") == 1
        assert await service.get_rep_id_by_name(session, "Wang Fang") == 3

    await engine.dispose()


@pytest.mark.asyncio
async def test_sales_query_service_returns_ranking_trend_and_anomaly_helpers():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

        service = SalesQueryService()
        start = date(2026, 1, 1)
        end = date(2026, 1, 31)

        assert await service.query_rep_ranking(session, start, end, top_n=1) == [
            RepSalesDTO(
                rep_id=3,
                rep_name="Wang Fang",
                region_id=1,
                region_name="East",
                total_amount=Decimal("1500.00"),
                order_count=0,
            )
        ]
        assert await service.query_region_ranking(session, start, end) == [
            RegionSalesDTO(
                region_id=1,
                region_name="East",
                total_amount=Decimal("2500.00"),
                order_count=0,
                total_profit=Decimal("0"),
            )
        ]
        assert await service.query_product_ranking(session, start, end, top_n=1) == [
            ProductSalesDTO(
                product_id=1,
                sku_code="SKU-1001",
                product_name="Laptop",
                category="Digital",
                total_amount=Decimal("2500.00"),
                total_quantity=3,
            )
        ]
        assert await service.query_monthly_trend(session, region_id=1, months=1, today=date(2026, 1, 31)) == [
            MonthlyTrendDTO(month="2026-01", total_amount=Decimal("2500.00"), order_count=2)
        ]
        assert service.calc_growth_rate(Decimal("120"), Decimal("100")) == Decimal("20.00")
        assert service.calc_growth_rate(Decimal("120"), Decimal("0")) is None
        assert await service.query_last_order_date(session, product_id=1) == date(2026, 1, 15)
        assert await service.query_order_count(session, region_id=1, start=start, end=end) == 2
        assert await service.query_refund_rates(session, start, end) == [(2, 1, 2), (3, 0, 1)]

        anomaly = AnomalyDTO(
            type="ORDER_DROP",
            severity="HIGH",
            subject="East",
            description="Order count dropped",
            suggestion="Review pipeline",
        )
        assert anomaly.model_dump() == {
            "type": "ORDER_DROP",
            "severity": "HIGH",
            "subject": "East",
            "description": "Order count dropped",
            "suggestion": "Review pipeline",
        }

    await engine.dispose()


def _sample_rows():
    return [
        SalesRegion(id=1, name="East"),
        SalesRep(id=2, name="Zhang Wei", region_id=1, role="SALES_REP", email="zhangwei@example.com"),
        SalesRep(id=3, name="Wang Fang", region_id=1, role="SALES_REP", email="wangfang@example.com"),
        Product(
            id=1,
            sku_code="SKU-1001",
            name="Laptop",
            category="Digital",
            unit_price=Decimal("6999.00"),
            cost=Decimal("4200.00"),
            status="ACTIVE",
        ),
        Product(
            id=2,
            sku_code="SKU-1002",
            name="Phone",
            category="Digital",
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
            product_id=2,
            region_id=1,
            customer_name="Nanjing Sports",
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
            customer_name="Hangzhou Flagship",
            quantity=1,
            unit_price=Decimal("1500.00"),
            amount=Decimal("1500.00"),
            cost=Decimal("900.00"),
            profit=Decimal("600.00"),
            status="COMPLETED",
            order_date=date(2026, 1, 15),
        ),
    ]
