"""工具调用日志模块

记录工具调用的开始、完成、失败事件，支持耗时统计和错误码识别。
"""
from time import perf_counter
from typing import Any

from app.core.logging import format_kv, get_logger


logger = get_logger("sales_agent.tools")


def tool_call_started(tool_name: str, arguments: dict[str, Any]) -> float:
    """记录工具调用开始日志，返回高精度时间戳用于后续耗时计算。

    Args:
        tool_name: 工具名称，如 "query_sales"、"generate_chart"
        arguments: 工具调用参数（仅记录序列化长度，不暴露内容）

    Returns:
        perf_counter 返回的起始时间戳（秒）
    """
    logger.info(
        format_kv(
            "tool_call_started",
            toolName=tool_name,
            argumentsLength=len(str(arguments)),
        )
    )
    return perf_counter()


def tool_call_finished(tool_name: str, started_at: float, result: str) -> str:
    """记录工具调用完成日志（成功或失败），并返回原始结果。

    Args:
        tool_name: 工具名称
        started_at: tool_call_started 返回的起始时间戳
        result: 工具执行结果文本（成功时为正常输出，失败时以错误码开头）

    Returns:
        原始结果字符串，供上层透传给 Agent
    """
    duration_ms = int((perf_counter() - started_at) * 1000)
    error_code = _error_prefix(result)
    if error_code:
        logger.warning(
            format_kv(
                "tool_call_failed",
                toolName=tool_name,
                durationMs=duration_ms,
                errorCode=error_code,
                resultLength=len(result),
            )
        )
    else:
        logger.info(
            format_kv(
                "tool_call_completed",
                toolName=tool_name,
                durationMs=duration_ms,
                resultLength=len(result),
            )
        )
    return result


def _error_prefix(result: str) -> str | None:
    """从结果首行提取错误码，无错误时返回 None。

    错误码约定：以 "TOOL_" 或 "NO_PERMISSION_" 开头的标识符。
    """
    first_line = result.splitlines()[0] if result else ""
    if first_line.startswith("TOOL_") or first_line.startswith("NO_PERMISSION_"):
        return first_line
    return None

