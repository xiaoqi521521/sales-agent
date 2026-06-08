from decimal import Decimal

from app.core.config import Settings
from app.core.token_usage import TokenUsage, calculate_estimated_cost, summarize_usage_metadata


def test_calculate_token_cost_uses_per_million_prices_and_cache_discount():
    settings = Settings(
        token_input_price_per_1m=Decimal("1"),
        token_cached_input_price_per_1m=Decimal("0.2"),
        token_output_price_per_1m=Decimal("2"),
    )
    usage = TokenUsage(
        input_tokens=1_000_000,
        cached_input_tokens=200_000,
        output_tokens=500_000,
        total_tokens=1_500_000,
    )

    assert calculate_estimated_cost(usage, settings) == Decimal("1.840000")


def test_summarize_usage_metadata_extracts_cached_input_tokens():
    metadata = {
        "deepseek-v4-flash": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
            "input_token_details": {"cache_read": 200},
        }
    }

    usage = summarize_usage_metadata(metadata)

    assert usage == TokenUsage(
        input_tokens=1000,
        cached_input_tokens=200,
        output_tokens=500,
        total_tokens=1500,
    )

