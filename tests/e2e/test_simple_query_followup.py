import pytest

from tests.e2e.conftest import auth_headers


@pytest.mark.asyncio
async def test_simple_query_followup_uses_session_memory(e2e_client):
    headers = await auth_headers(e2e_client, rep_id=5)

    first = await e2e_client.post(
        "/agent/chat",
        json={"sessionId": "e2e-followup-a", "message": "上个月华东区销售员排行怎么样？"},
        headers=headers,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["sessionId"] == "e2e-followup-a"
    assert "Wang Fang" in first_body["reply"]
    assert first_body["toolCalls"][0]["name"] == "calculate_sales_summary"

    followup = await e2e_client.post(
        "/agent/chat",
        json={"sessionId": "e2e-followup-a", "message": "第一名的订单明细给我看看"},
        headers=headers,
    )
    assert followup.status_code == 200
    followup_body = followup.json()
    assert "Wang Fang" in followup_body["reply"]
    assert "ORD-002" in followup_body["reply"]
    assert "ORD-001" not in followup_body["reply"]
    assert followup_body["toolCalls"][0]["name"] == "query_sales_orders"


@pytest.mark.asyncio
async def test_different_sessions_do_not_share_followup_memory(e2e_client):
    headers = await auth_headers(e2e_client, rep_id=5)

    await e2e_client.post(
        "/agent/chat",
        json={"sessionId": "e2e-isolated-a", "message": "上个月华东区销售员排行怎么样？"},
        headers=headers,
    )
    isolated_followup = await e2e_client.post(
        "/agent/chat",
        json={"sessionId": "e2e-isolated-b", "message": "第一名的订单明细给我看看"},
        headers=headers,
    )

    assert isolated_followup.status_code == 200
    body = isolated_followup.json()
    assert "缺少上下文" in body["reply"]
    assert body["toolCalls"] == []


@pytest.mark.asyncio
async def test_e2e_role_permissions_filter_visible_orders(e2e_client):
    rep_headers = await auth_headers(e2e_client, rep_id=2)
    director_headers = await auth_headers(e2e_client, rep_id=5)

    rep_response = await e2e_client.post(
        "/agent/chat",
        json={"sessionId": "e2e-permission-rep", "message": "查看1月所有订单"},
        headers=rep_headers,
    )
    director_response = await e2e_client.post(
        "/agent/chat",
        json={"sessionId": "e2e-permission-director", "message": "查看1月所有订单"},
        headers=director_headers,
    )

    assert rep_response.status_code == 200
    assert director_response.status_code == 200
    rep_reply = rep_response.json()["reply"]
    director_reply = director_response.json()["reply"]
    assert "ORD-001" in rep_reply
    assert "ORD-002" not in rep_reply
    assert "ORD-009" not in rep_reply
    assert "ORD-001" in director_reply
    assert "ORD-002" in director_reply
    assert "ORD-009" in director_reply
