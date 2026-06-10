import json

import pytest

from tests.e2e.conftest import auth_headers


@pytest.mark.asyncio
async def test_chart_generation_returns_frontend_consumable_chart_json(e2e_client):
    headers = await auth_headers(e2e_client, rep_id=5)

    response = await e2e_client.post(
        "/agent/chat",
        json={"sessionId": "e2e-chart", "message": "生成1月各大区销售占比图表"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["toolCalls"][0]["name"] == "generate_sales_chart"
    chart_payload = body["toolCalls"][0]["summary"].removeprefix("CHART_JSON:")
    option = json.loads(chart_payload)
    assert option["series"][0]["type"] == "pie"
    assert option["title"]["text"] == "Region Share"


@pytest.mark.asyncio
async def test_anomaly_warning_returns_stable_business_alerts(e2e_client):
    headers = await auth_headers(e2e_client, rep_id=5)

    response = await e2e_client.post(
        "/agent/chat",
        json={"sessionId": "e2e-anomaly", "message": "检查当前销售异常预警"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["toolCalls"][0]["name"] == "detect_sales_anomalies"
    assert "异常" in body["reply"]
    assert "正常" not in body["reply"]
