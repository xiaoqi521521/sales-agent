from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_memory import ChatMemory
from app.repositories.base_repository import BaseRepository


class ChatMemoryRepository(BaseRepository[ChatMemory]):
    def __init__(self) -> None:
        super().__init__(ChatMemory)

    async def find_by_session_id(self, session: AsyncSession, session_id: str) -> ChatMemory | None:
        result = await session.execute(select(ChatMemory).where(ChatMemory.session_id == session_id))
        return result.scalars().first()

    async def save_messages(self, session: AsyncSession, session_id: str, messages: str) -> ChatMemory:
        memory = await self.find_by_session_id(session, session_id)
        if memory is None:
            memory = ChatMemory(session_id=session_id, messages=messages)
            session.add(memory)
        else:
            memory.messages = messages
        await session.flush()
        return memory

    async def delete_by_session_id(self, session: AsyncSession, session_id: str) -> None:
        await session.execute(delete(ChatMemory).where(ChatMemory.session_id == session_id))
