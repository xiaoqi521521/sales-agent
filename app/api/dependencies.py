"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runtime import SalesAgentRuntime
from app.core.database import get_db_session


async def get_sales_agent_runtime(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SalesAgentRuntime:
    return SalesAgentRuntime(session=session)
