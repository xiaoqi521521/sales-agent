from typing import Literal

from pydantic import BaseModel, Field


class SalesQueryInput(BaseModel):
    start_date: str = Field(description="查询开始日期，格式 yyyy-MM-dd，如 2026-01-01")
    end_date: str = Field(description="查询结束日期，格式 yyyy-MM-dd，如 2026-01-31")
    region_name: str | None = Field(default=None, description="大区名称；空字符串或 null 表示查全公司")
    rep_name: str | None = Field(default=None, description="销售员姓名；空字符串或 null 表示不限销售员")
    customer_name: str | None = Field(default=None, description="客户名称关键词；空字符串或 null 表示不限客户")
    limit: int = Field(default=20, description="最多返回条数，默认 20，最大 50")


class SalesSummaryInput(BaseModel):
    summary_type: Literal["total", "rep_ranking", "region_ranking", "product_ranking"] = Field(
        description="汇总类型：total 总销售额，rep_ranking 销售员排名，region_ranking 大区排名，product_ranking 产品排名"
    )
    start_date: str = Field(description="查询开始日期，格式 yyyy-MM-dd")
    end_date: str = Field(description="查询结束日期，格式 yyyy-MM-dd")
    region_name: str | None = Field(default=None, description="大区名称；仅部分汇总类型使用，空字符串或 null 表示全公司")
    top_n: int = Field(default=5, description="返回前 N 名，默认 5，最大 20；产品排名传负数表示查最差 N 名")


class SalesTrendInput(BaseModel):
    trend_type: Literal["mom", "yoy", "monthly"] = Field(
        description="趋势类型：mom 环比，yoy 同比，monthly 月度趋势"
    )
    current_start: str | None = Field(default=None, description="当前周期开始日期，格式 yyyy-MM-dd；mom/yoy 使用")
    current_end: str | None = Field(default=None, description="当前周期结束日期，格式 yyyy-MM-dd；mom/yoy 使用")
    previous_start: str | None = Field(default=None, description="对比周期开始日期；mom 可空，空则自动计算上一个等长周期")
    previous_end: str | None = Field(default=None, description="对比周期结束日期；mom 可空，空则自动计算上一个等长周期")
    region_name: str | None = Field(default=None, description="大区名称；空字符串或 null 表示全公司")
    months: int = Field(default=6, description="月度趋势查看近多少个月，最大 24")


class SalesChartInput(BaseModel):
    chart_type: Literal["line", "bar", "pie"] = Field(description="图表类型：line 折线图，bar 柱状图，pie 饼图")
    dimension: Literal["region", "rep", "category"] = Field(
        default="region",
        description="图表维度：region 大区，rep 销售员，category 品类",
    )
    start_date: str | None = Field(default=None, description="查询开始日期，格式 yyyy-MM-dd；bar/pie 使用")
    end_date: str | None = Field(default=None, description="查询结束日期，格式 yyyy-MM-dd；bar/pie 使用")
    months: int = Field(default=6, description="折线图查看近多少个月，最大 24")
    region_name: str | None = Field(default=None, description="折线图可指定大区；空字符串或 null 表示全公司")
    title: str | None = Field(default=None, description="图表标题")
