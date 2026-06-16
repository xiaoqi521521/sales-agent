from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db_session
from app.core.user_context import get_current_user as get_request_user
from app.main import app
from app.models.base import Base
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep


@pytest.mark.asyncio
async def test_auth_login_returns_bearer_token_for_sales_rep():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(
            [
                SalesRegion(id=1, name="East"),
                SalesRep(id=3, name="Zhang Wei", region_id=1, role="SALES_REP", email="zhangwei@example.com"),
            ]
        )
        await session.commit()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/login", json={"repId": 3})

    app.dependency_overrides.clear()
    await engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["tokenType"] == "bearer"
    assert body["accessToken"]
    assert body["user"] == {
        "repId": 3,
        "username": "Zhang Wei",
        "role": "SALES_REP",
        "regionId": 1,
    }


@pytest.mark.asyncio
async def test_agent_chat_requires_bearer_token():
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/agent/chat",
            json={"sessionId": "auth-session-001", "message": "hello"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_request_clears_current_user_context_after_response(monkeypatch):
    from app.agent.runtime import AgentRunResult

    class FakeRuntime:
        def __init__(self, **kwargs):
            pass

        async def chat_with_trace(self, *, session_id: str, message: str) -> AgentRunResult:
            assert get_request_user() is not None
            return AgentRunResult(reply="ok")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(
            [
                SalesRegion(id=1, name="East"),
                SalesRep(id=3, name="Zhang Wei", region_id=1, role="SALES_REP", email="zhangwei@example.com"),
            ]
        )
        await session.commit()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    monkeypatch.setattr("app.api.dependencies.SalesAgentRuntime", FakeRuntime)
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login = await client.post("/auth/login", json={"repId": 3})
            response = await client.post(
                "/agent/chat",
                json={"sessionId": "auth-context-session", "message": "hello"},
                headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
            )
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert response.status_code == 200
    assert get_request_user() is None
