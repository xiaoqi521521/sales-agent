from httpx import ASGITransport, AsyncClient
import pytest

from app.api.dependencies import get_current_user, get_sales_agent_runtime
from app.core.auth_context import CurrentUser
from app.main import app


def fake_current_user() -> CurrentUser:
    return CurrentUser(
        username="Test Director",
        role="SALES_DIRECTOR",
        region_id=None,
        rep_id=99,
    )


class FailingRuntime:
    async def chat_with_trace(self, *, session_id: str, message: str):
        raise RuntimeError("internal stack trace should not be returned")


@pytest.mark.asyncio
async def test_agent_chat_unhandled_exception_returns_stable_error_response():
    app.dependency_overrides[get_sales_agent_runtime] = lambda: FailingRuntime()
    app.dependency_overrides[get_current_user] = fake_current_user
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/agent/chat",
            json={"sessionId": "err-session-001", "message": "触发异常"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "success": False,
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "服务暂时不可用，请稍后重试",
        },
    }
    assert "RuntimeError" not in response.text
    assert "stack trace" not in response.text


@pytest.mark.asyncio
async def test_request_validation_error_returns_stable_error_response():
    app.dependency_overrides[get_sales_agent_runtime] = lambda: FailingRuntime()
    app.dependency_overrides[get_current_user] = fake_current_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/agent/chat",
            json={"sessionId": "validation-session-001"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "请求参数校验失败"

