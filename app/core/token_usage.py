from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.core.config import Settings
from app.core.logging import format_kv, get_logger


logger = get_logger("sales_agent.token_usage")


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


def summarize_usage_metadata(metadata: dict[str, Any] | None) -> TokenUsage:
    """汇总 Token 用量元数据，支持单层或嵌套多模型结构的聚合统计。"""
    if not metadata:
        return TokenUsage()

    if "input_tokens" in metadata or "output_tokens" in metadata or "total_tokens" in metadata:
        return _usage_from_mapping(metadata)

    totals = TokenUsage()
    input_tokens = 0
    cached_input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    for usage in metadata.values():
        if not isinstance(usage, dict):
            continue
        item = _usage_from_mapping(usage)
        item_input = item.input_tokens
        item_output = item.output_tokens
        item_total = item.total_tokens
        input_tokens += item_input
        cached_input_tokens += item.cached_input_tokens
        output_tokens += item_output
        total_tokens += item_total
    return TokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=min(cached_input_tokens, input_tokens),
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def calculate_estimated_cost(usage: TokenUsage, settings: Settings) -> Decimal:
    """根据用量和定价配置计算预估费用，区分普通输入与缓存输入的单价。"""
    normal_input_tokens = max(usage.input_tokens - usage.cached_input_tokens, 0)
    cost = (
        Decimal(normal_input_tokens) / Decimal(1_000_000) * settings.token_input_price_per_1m
        + Decimal(usage.cached_input_tokens) / Decimal(1_000_000) * settings.token_cached_input_price_per_1m
        + Decimal(usage.output_tokens) / Decimal(1_000_000) * settings.token_output_price_per_1m
    )
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def log_token_usage(
    *,
    session_id: str,
    model_name: str,
    usage: TokenUsage,
    settings: Settings,
) -> Decimal:
    """记录 Token 用量日志并返回预估费用，超阈值时触发告警。"""
    if usage.total_tokens <= 0:
        logger.info(format_kv("token_usage_unavailable", sessionId=session_id, model=model_name))
        return Decimal("0.000000")

    estimated_cost = calculate_estimated_cost(usage, settings)
    logger.info(
        format_kv(
            "token_usage",
            sessionId=session_id,
            model=model_name,
            inputTokens=usage.input_tokens,
            cachedInputTokens=usage.cached_input_tokens,
            outputTokens=usage.output_tokens,
            totalTokens=usage.total_tokens,
            estimatedCost=f"{estimated_cost:.6f}",
            currency=settings.token_cost_currency,
        )
    )
    if _threshold_exceeded(usage, estimated_cost, settings):
        logger.warning(
            format_kv(
                "token_cost_threshold_exceeded",
                totalTokens=usage.total_tokens,
                estimatedCost=f"{estimated_cost:.6f}",
            )
        )
    return estimated_cost


def _threshold_exceeded(usage: TokenUsage, cost: Decimal, settings: Settings) -> bool:
    """判断用量或费用是否超过配置的告警阈值（任一超出即返回 True）。"""
    return (
        settings.token_warn_total_threshold > 0
        and usage.total_tokens > settings.token_warn_total_threshold
    ) or (
        settings.token_warn_cost_threshold > 0
        and cost > settings.token_warn_cost_threshold
    )


def _to_int(value: Any) -> int:
    """安全转换为 int，无效值返回 0。"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _usage_from_mapping(usage: dict[str, Any]) -> TokenUsage:
    """从字典解析 Token 用量，自动补全缺失字段并处理缓存输入明细。"""
    input_tokens = _to_int(usage.get("input_tokens"))
    output_tokens = _to_int(usage.get("output_tokens"))
    total_tokens = _to_int(usage.get("total_tokens")) or input_tokens + output_tokens
    details = usage.get("input_token_details") if isinstance(usage.get("input_token_details"), dict) else {}
    cached_input_tokens = min(_to_int(details.get("cache_read")), input_tokens)
    return TokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
