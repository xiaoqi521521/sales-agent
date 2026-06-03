from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.repositories.base_repository import BaseRepository


class ProductRepository(BaseRepository[Product]):
    def __init__(self) -> None:
        super().__init__(Product)

    async def find_by_sku_code(self, session: AsyncSession, sku_code: str) -> Product | None:
        result = await session.execute(select(Product).where(Product.sku_code == sku_code))
        return result.scalars().first()

    async def find_by_category(self, session: AsyncSession, category: str) -> list[Product]:
        result = await session.execute(select(Product).where(Product.category == category).order_by(Product.id))
        return list(result.scalars().all())

    async def find_by_status(self, session: AsyncSession, status: str) -> list[Product]:
        result = await session.execute(select(Product).where(Product.status == status).order_by(Product.id))
        return list(result.scalars().all())
