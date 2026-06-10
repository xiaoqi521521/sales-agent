import pytest

from tests.e2e.conftest import auth_headers


@pytest.mark.asyncio
async def test_multi_step_reasoning_calls_summary_trend_and_ranking_tools(e2e_client):
    headers = await auth_headers(e2e_client, rep_id=5)

    response = await e2e_client.post(
        "/agent/chat",
        json={
            "sessionId": "e2e-multi-step",
            "message": "综合分析华东区1月销售额、环比和销售员排行",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    tool_names = [item["name"] for item in body["toolCalls"]]
    assert tool_names == [
        "calculate_sales_summary",
        "analyze_sales_trend",
        "calculate_sales_summary",
    ]
    assert "综合分析完成" in body["reply"]
    assert "Wang Fang" in body["reply"]
    assert "环比" in body["reply"]
