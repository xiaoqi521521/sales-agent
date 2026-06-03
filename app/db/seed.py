from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep


async def seed_sales_data(session: AsyncSession) -> None:
    regions = [
        SalesRegion(id=1, name="East China", code="EAST"),
        SalesRegion(id=2, name="South China", code="SOUTH"),
        SalesRegion(id=3, name="North China", code="NORTH"),
    ]
    reps = [
        SalesRep(id=1, name="Zhang Lei", region_id=1),
        SalesRep(id=2, name="Wang Fang", region_id=1),
        SalesRep(id=3, name="Li Ming", region_id=2),
        SalesRep(id=4, name="Chen Yu", region_id=3),
    ]
    products = [
        Product(id=1, name="Laptop Pro", category="Digital", unit_price=8999.00),
        Product(id=2, name="Smart Phone", category="Digital", unit_price=4999.00),
        Product(id=3, name="Air Conditioner", category="Appliance", unit_price=3299.00),
        Product(id=4, name="Business Jacket", category="Apparel", unit_price=899.00),
    ]
    orders = [
        SalesOrder(
            id=1,
            order_no="SO-2025-1001",
            region_id=1,
            sales_rep_id=1,
            product_id=1,
            order_date=date(2025, 10, 5),
            quantity=10,
            amount=89990.00,
            status="COMPLETED",
        ),
        SalesOrder(
            id=2,
            order_no="SO-2025-1002",
            region_id=1,
            sales_rep_id=2,
            product_id=2,
            order_date=date(2025, 10, 8),
            quantity=18,
            amount=89982.00,
            status="COMPLETED",
        ),
        SalesOrder(
            id=3,
            order_no="SO-2025-1003",
            region_id=2,
            sales_rep_id=3,
            product_id=3,
            order_date=date(2025, 10, 12),
            quantity=12,
            amount=39588.00,
            status="COMPLETED",
        ),
        SalesOrder(
            id=4,
            order_no="SO-2025-1004",
            region_id=3,
            sales_rep_id=4,
            product_id=4,
            order_date=date(2025, 10, 16),
            quantity=30,
            amount=26970.00,
            status="COMPLETED",
        ),
        SalesOrder(
            id=5,
            order_no="SO-2025-1101",
            region_id=1,
            sales_rep_id=1,
            product_id=1,
            order_date=date(2025, 11, 5),
            quantity=14,
            amount=125986.00,
            status="COMPLETED",
        ),
        SalesOrder(
            id=6,
            order_no="SO-2025-1102",
            region_id=1,
            sales_rep_id=2,
            product_id=3,
            order_date=date(2025, 11, 9),
            quantity=8,
            amount=26392.00,
            status="COMPLETED",
        ),
        SalesOrder(
            id=7,
            order_no="SO-2025-1103",
            region_id=2,
            sales_rep_id=3,
            product_id=2,
            order_date=date(2025, 11, 13),
            quantity=20,
            amount=99980.00,
            status="COMPLETED",
        ),
        SalesOrder(
            id=8,
            order_no="SO-2025-1104",
            region_id=3,
            sales_rep_id=4,
            product_id=4,
            order_date=date(2025, 11, 18),
            quantity=6,
            amount=5394.00,
            status="RETURNED",
        ),
    ]

    session.add_all([*regions, *reps, *products, *orders])
