import pytest
from pydantic import ValidationError

from app.tools.schemas import SalesChartInput, SalesQueryInput, SalesSummaryInput, SalesTrendInput


def test_query_input_rejects_sql_like_region_name():
    with pytest.raises(ValidationError):
        SalesQueryInput(
            start_date="2026-01-01",
            end_date="2026-01-31",
            region_name="'; DROP TABLE sales_order; --",
            limit=10,
        )


def test_query_input_rejects_unknown_region_name():
    with pytest.raises(ValidationError):
        SalesQueryInput(
            start_date="2026-01-01",
            end_date="2026-01-31",
            region_name="不存在的大区",
            limit=10,
        )


def test_query_input_rejects_invalid_date_format_and_order():
    with pytest.raises(ValidationError):
        SalesQueryInput(
            start_date="2026/01/01",
            end_date="2026-01-31",
            region_name="华东区",
            limit=10,
        )

    with pytest.raises(ValidationError):
        SalesQueryInput(
            start_date="2026-02-01",
            end_date="2026-01-31",
            region_name="华东区",
            limit=10,
        )


def test_numeric_boundaries_reject_out_of_range_values():
    with pytest.raises(ValidationError):
        SalesQueryInput(start_date="2026-01-01", end_date="2026-01-31", limit=1000)

    with pytest.raises(ValidationError):
        SalesSummaryInput(
            summary_type="product_ranking",
            start_date="2026-01-01",
            end_date="2026-01-31",
            top_n=0,
        )

    with pytest.raises(ValidationError):
        SalesTrendInput(trend_type="monthly", months=100)

    with pytest.raises(ValidationError):
        SalesChartInput(chart_type="line", months=100)


def test_whitelisted_values_pass_schema_validation():
    query = SalesQueryInput(
        start_date="2026-01-01",
        end_date="2026-01-31",
        region_name=" 华东区 ",
        limit=50,
    )
    assert query.region_name == "华东区"

    summary = SalesSummaryInput(
        summary_type="product_ranking",
        start_date="2026-01-01",
        end_date="2026-01-31",
        region_name="华南区",
        top_n=-5,
    )
    assert summary.top_n == -5

    chart = SalesChartInput(chart_type="bar", dimension="region", start_date="2026-01-01", end_date="2026-01-31")
    assert chart.dimension == "region"
