from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales_region import SalesRegion
from app.repositories.base_repository import BaseRepository


class SalesRegionRepository(BaseRepository[SalesRegion]):
    def __init__(self) -> None:
        super().__init__(SalesRegion)

    async def find_by_name(self, session: AsyncSession, name: str) -> SalesRegion | None:
        result = await session.execute(select(SalesRegion).where(SalesRegion.name == name))
        return result.scalars().first()
