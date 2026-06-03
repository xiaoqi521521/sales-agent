from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT]) -> None:
        self.model = model

    async def find_by_id(self, session: AsyncSession, entity_id: int) -> ModelT | None:
        return await session.get(self.model, entity_id)

    async def find_all(self, session: AsyncSession) -> list[ModelT]:
        result = await session.execute(select(self.model).order_by(self.model.id))
        return list(result.scalars().all())
