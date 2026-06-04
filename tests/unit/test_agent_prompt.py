from datetime import date

from app.agent.prompts import build_system_prompt


def test_system_prompt_matches_sales_agent_boundaries():
    prompt = build_system_prompt(date(2026, 2, 15))

    assert "专业的销售数据分析助手" in prompt
    assert "今天是 2026-02-15" in prompt
    assert "只能查询数据，不能修改任何数据" in prompt
    assert "不能预测未来销售" in prompt
    assert "用中文回答" in prompt
    assert "金额格式化为 ¥X,XXX" in prompt
    assert "CHART_JSON:" in prompt
    assert "不得修改、截断、改写或省略" in prompt
    assert "充分利用对话历史理解用户意图" in prompt
