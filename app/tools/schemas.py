import re
from datetime import date
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ALLOWED_REGION_NAMES = frozenset({"华东区", "华南区", "华北区", "西南区"})
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_ERROR = "日期格式错误，请使用 yyyy-MM-dd 格式，例如：2026-01-01。"
DATE_ORDER_ERROR = "日期范围错误，开始日期不能晚于结束日期。"
REGION_ERROR = "大区名称不在允许范围内，请使用：华东区、华南区、华北区、西南区。"


def _normalize_region_name(value: str | None) -> str | None:
    """校验并标准化区域名称，空值返回None，非法值抛出异常。"""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped not in ALLOWED_REGION_NAMES:
        raise ValueError(REGION_ERROR)
    return stripped


def _parse_optional_date(value: str | None) -> date | None:
    """将日期字符串解析为date对象，格式不合法则抛出异常。"""
    if value is None:
        return None
    if not DATE_PATTERN.fullmatch(value):
        raise ValueError(DATE_ERROR)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(DATE_ERROR) from exc


def _validate_optional_date(value: str | None) -> str | None:
    """校验日期字符串格式，通过则原样返回。"""
    if value is not None:
        _parse_optional_date(value)
    return value


def _validate_date_order(start_date: str | None, end_date: str | None) -> None:
    """校验起始日期不早于结束日期，任一为空则跳过。"""
    if start_date is None or end_date is None:
        return
    start = _parse_optional_date(start_date)
    end = _parse_optional_date(end_date)
    if start is not None and end is not None and start > end:
        raise ValueError(DATE_ORDER_ERROR)


class ToolInputModel(BaseModel):
    date_fields: ClassVar[tuple[str, ...]] = ()

    @field_validator("region_name", mode="before", check_fields=False)
    @classmethod
    def validate_region_name(cls, value: str | None) -> str | None:
        return _normalize_region_name(value)

    @field_validator("*", mode="after")
    @classmethod
    def validate_date_format(cls, value, info):
        if info.field_name in cls.date_fields:
            return _validate_optional_date(value)
        return value


class SalesQueryInput(ToolInputModel):
    date_fields: ClassVar[tuple[str, ...]] = ("start_date", "end_date")

    start_date: str = Field(description="查询开始日期，格式 yyyy-MM-dd，如 2026-01-01")
    end_date: str = Field(description="查询结束日期，格式 yyyy-MM-dd，如 2026-01-31")
    region_name: str | None = Field(default=None, description="大区名称；空字符串或 null 表示查全公司")
    rep_name: str | None = Field(default=None, description="销售员姓名；空字符串或 null 表示不限销售员")
    customer_name: str | None = Field(default=None, description="客户名称关键词；空字符串或 null 表示不限客户")
    limit: int = Field(default=20, ge=1, le=50, description="最多返回条数，默认 20，最大 50")

    @model_validator(mode="after")
    def validate_date_range(self):
        _validate_date_order(self.start_date, self.end_date)
        return self


class SalesSummaryInput(ToolInputModel):
    date_fields: ClassVar[tuple[str, ...]] = ("start_date", "end_date")

    summary_type: Literal["total", "rep_ranking", "region_ranking", "product_ranking"] = Field(
        description="汇总类型：total 总销售额，rep_ranking 销售员排名，region_ranking 大区排名，product_ranking 产品排名"
    )
    start_date: str = Field(description="查询开始日期，格式 yyyy-MM-dd")
    end_date: str = Field(description="查询结束日期，格式 yyyy-MM-dd")
    region_name: str | None = Field(default=None, description="大区名称；仅部分汇总类型使用，空字符串或 null 表示全公司")
    top_n: int = Field(default=5, ge=-20, le=20, description="返回前 N 名，默认 5，最大 20；产品排名传负数表示查最差 N 名")

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, value: int) -> int:
        if value == 0:
            raise ValueError("top_n 不能为 0。")
        return value

    @model_validator(mode="after")
    def validate_date_range(self):
        _validate_date_order(self.start_date, self.end_date)
        return self


class SalesTrendInput(ToolInputModel):
    date_fields: ClassVar[tuple[str, ...]] = ("current_start", "current_end", "previous_start", "previous_end")

    trend_type: Literal["mom", "yoy", "monthly"] = Field(
        description="趋势类型：mom 环比，yoy 同比，monthly 月度趋势"
    )
    current_start: str | None = Field(default=None, description="当前周期开始日期，格式 yyyy-MM-dd；mom/yoy 使用")
    current_end: str | None = Field(default=None, description="当前周期结束日期，格式 yyyy-MM-dd；mom/yoy 使用")
    previous_start: str | None = Field(default=None, description="对比周期开始日期；mom 可空，空则自动计算上一个等长周期")
    previous_end: str | None = Field(default=None, description="对比周期结束日期；mom 可空，空则自动计算上一个等长周期")
    region_name: str | None = Field(default=None, description="大区名称；空字符串或 null 表示全公司")
    rep_name: str | None = Field(default=None, description="销售员姓名；空字符串或 null 表示不限销售员")
    months: int = Field(default=6, ge=1, le=24, description="月度趋势查看近多少个月，最大 24")

    @model_validator(mode="after")
    def validate_date_ranges(self):
        _validate_date_order(self.current_start, self.current_end)
        _validate_date_order(self.previous_start, self.previous_end)
        return self


class SalesChartInput(ToolInputModel):
    date_fields: ClassVar[tuple[str, ...]] = ("start_date", "end_date")

    chart_type: Literal["line", "bar", "pie"] = Field(description="图表类型：line 折线图，bar 柱状图，pie 饼图")
    dimension: Literal["region", "rep", "category"] = Field(
        default="region",
        description="图表维度：region 大区，rep 销售员，category 品类",
    )
    start_date: str | None = Field(default=None, description="查询开始日期，格式 yyyy-MM-dd；bar/pie 使用")
    end_date: str | None = Field(default=None, description="查询结束日期，格式 yyyy-MM-dd；bar/pie 使用")
    months: int = Field(default=6, ge=1, le=24, description="折线图查看近多少个月，最大 24")
    region_name: str | None = Field(default=None, description="折线图可指定大区；空字符串或 null 表示全公司")
    title: str | None = Field(default=None, description="图表标题")

    @model_validator(mode="after")
    def validate_date_range(self):
        _validate_date_order(self.start_date, self.end_date)
        return self
