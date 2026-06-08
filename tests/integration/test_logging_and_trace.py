import logging

from httpx import ASGITransport, AsyncClient
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_response_includes_generated_trace_id_and_request_log(caplog):
    caplog.set_level(logging.INFO)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.headers["x-trace-id"]
    assert "event=http_request_completed" in caplog.text
    assert "method=GET" in caplog.text
    assert "path=/health" in caplog.text
    assert "statusCode=200" in caplog.text
    assert "durationMs=" in caplog.text


@pytest.mark.asyncio
async def test_request_log_separator_is_printed_before_request_started(caplog):
    caplog.set_level(logging.INFO)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    separator = "=" * 80
    assert separator in caplog.text
    assert caplog.text.index(separator) < caplog.text.index("event=http_request_started")


@pytest.mark.asyncio
async def test_agent_chat_reuses_trace_id_and_does_not_log_authorization(caplog):
    from app.agent.runtime import AgentRunResult
    from app.api.dependencies import get_current_user, get_sales_agent_runtime
    from app.core.auth_context import CurrentUser

    class FakeRuntime:
        async def chat_with_trace(self, *, session_id: str, message: str) -> AgentRunResult:
            return AgentRunResult(reply="ok")

    def fake_current_user() -> CurrentUser:
        return CurrentUser(username="Test Director", role="SALES_DIRECTOR", region_id=None, rep_id=99)

    caplog.set_level(logging.INFO)
    app.dependency_overrides[get_sales_agent_runtime] = lambda: FakeRuntime()
    app.dependency_overrides[get_current_user] = fake_current_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/agent/chat",
            json={"sessionId": "trace-session-001", "message": "hello"},
            headers={
                "X-Trace-Id": "trace-test-001",
                "Authorization": "Bearer secret-jwt-value",
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["x-trace-id"] == "trace-test-001"
    assert "traceId=trace-test-001" in caplog.text
    assert "secret-jwt-value" not in caplog.text
    assert "Authorization" not in caplog.text
