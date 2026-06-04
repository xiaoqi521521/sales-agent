from datetime import date
from decimal import Decimal


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def clamp(value: int, minimum: int, maximum: int) -> int:
    return min(max(value, minimum), maximum)


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
        return "日期范围错误，开始日期不能晚于结束日期"
    return "日期格式错误，请使用 yyyy-MM-dd 格式，如：2026-01-01"
