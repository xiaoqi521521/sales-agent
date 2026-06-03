from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest

from app.db.seed import seed_sales_data
from app.models.base import Base
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep


@pytest.mark.asyncio
async def test_seed_sales_data_creates_core_sales_records():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        await seed_sales_data(session)
        await session.commit()

        regions = (await session.execute(select(SalesRegion))).scalars().all()
        reps = (await session.execute(select(SalesRep))).scalars().all()
        products = (await session.execute(select(Product))).scalars().all()
        orders = (await session.execute(select(SalesOrder))).scalars().all()

    await engine.dispose()

    assert len(regions) >= 3
    assert len(reps) >= 4
    assert len(products) >= 4
    assert len(orders) >= 8
