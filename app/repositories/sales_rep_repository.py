from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales_rep import SalesRep
from app.repositories.base_repository import BaseRepository


class SalesRepRepository(BaseRepository[SalesRep]):
    def __init__(self) -> None:
        super().__init__(SalesRep)

    async def find_by_region_id(self, session: AsyncSession, region_id: int) -> list[SalesRep]:
        result = await session.execute(
            select(SalesRep).where(SalesRep.region_id == region_id).order_by(SalesRep.id)
        )
        return list(result.scalars().all())

    async def find_by_role(self, session: AsyncSession, role: str) -> list[SalesRep]:
        result = await session.execute(select(SalesRep).where(SalesRep.role == role).order_by(SalesRep.id))
        return list(result.scalars().all())

    async def find_by_name(self, session: AsyncSession, name: str) -> SalesRep | None:
        result = await session.execute(select(SalesRep).where(SalesRep.name == name))
        return result.scalars().first()
