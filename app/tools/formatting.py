from datetime import date
from decimal import Decimal


class ToolBoundaryError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ToolUnknownEntityError(ToolBoundaryError):
    pass


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def format_money(value: Decimal) -> str:
    return f"¥{value:,.0f}"


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_required_range(start_date: str | None, end_date: str | None) -> tuple[date, date]:
    if not start_date or not end_date:
        raise ValueError("missing_date")
    start = parse_date(start_date)
    end = parse_date(end_date)
    if start > end:
        raise ValueError("date_order")
    return start, end


def translate_status(status: str) -> str:
    translations = {
        "COMPLETED": "已完成",
        "REFUNDED": "已退款",
        "CANCELLED": "已取消",
    }
    return translations.get(status, status)


def date_error_message(error: Exception) -> str:
    if isinstance(error, ValueError) and str(error) == "date_order":
        return tool_invalid_argument("日期范围错误，开始日期不能晚于结束日期。")
    return tool_invalid_argument("日期格式错误，请使用 yyyy-MM-dd 格式，例如：2026-01-01。")


def tool_empty_data(message: str) -> str:
    return f"TOOL_EMPTY_DATA\n{message}\n可能原因：该时段无交易、数据尚未录入，或查询条件过于严格。"


def tool_invalid_argument(message: str) -> str:
    return f"TOOL_INVALID_ARGUMENT\n{message}"


def tool_unknown_entity(entity_type: str, entity_name: str) -> str:
    return f"TOOL_UNKNOWN_ENTITY\n未找到{entity_type}：{entity_name}。请确认名称是否正确，或改用可访问范围内的名称。"


def tool_execution_error(message: str = "数据查询服务暂时不可用，请稍后重试。") -> str:
    return f"TOOL_EXECUTION_ERROR\n{message}"
