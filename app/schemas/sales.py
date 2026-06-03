from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SalesSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class OrderQueryParams(SalesSchema):
    rep_id: int | None = Field(default=None, alias="repId")
    region_id: int | None = Field(default=None, alias="regionId")
    product_id: int | None = Field(default=None, alias="productId")
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")


class OrderSummaryDTO(SalesSchema):
    order_no: str = Field(alias="orderNo")
    rep_name: str = Field(alias="repName")
    customer_name: str = Field(alias="customerName")
    amount: Decimal
    status: str
    order_date: date = Field(alias="orderDate")


class RepSalesDTO(SalesSchema):
    rep_id: int = Field(alias="repId")
    rep_name: str = Field(alias="repName")
    region_id: int = Field(alias="regionId")
    region_name: str = Field(alias="regionName")
    total_amount: Decimal = Field(alias="totalAmount")
    order_count: int = Field(alias="orderCount")


class RegionSalesDTO(SalesSchema):
    region_id: int = Field(alias="regionId")
    region_name: str = Field(alias="regionName")
    total_amount: Decimal = Field(alias="totalAmount")
    order_count: int = Field(alias="orderCount")
    total_profit: Decimal = Field(alias="totalProfit")


class ProductSalesDTO(SalesSchema):
    product_id: int = Field(alias="productId")
    sku_code: str = Field(alias="skuCode")
    product_name: str = Field(alias="productName")
    category: str
    total_amount: Decimal = Field(alias="totalAmount")
    total_quantity: int = Field(alias="totalQuantity")


class MonthlyTrendDTO(SalesSchema):
    month: str
    total_amount: Decimal = Field(alias="totalAmount")
    order_count: int = Field(alias="orderCount")


class AnomalyDTO(SalesSchema):
    type: str
    severity: str
    subject: str
    description: str
    suggestion: str
