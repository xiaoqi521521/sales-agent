from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, String

from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep


def test_sales_region_model_matches_mysql_table():
    assert SalesRegion.__tablename__ == "sa_sales_region"
    columns = SalesRegion.__table__.c

    assert isinstance(columns.id.type, BigInteger)
    assert isinstance(columns.name.type, String)
    assert columns.name.type.length == 50
    assert isinstance(columns.parent_region_id.type, BigInteger)
    assert isinstance(columns.created_at.type, DateTime)

    assert not SalesRegion.__table__.foreign_keys


def test_sales_rep_model_matches_mysql_table():
    assert SalesRep.__tablename__ == "sa_sales_rep"
    columns = SalesRep.__table__.c

    assert isinstance(columns.id.type, BigInteger)
    assert isinstance(columns.name.type, String)
    assert columns.name.type.length == 50
    assert isinstance(columns.region_id.type, BigInteger)
    assert isinstance(columns.role.type, String)
    assert columns.role.type.length == 20
    assert isinstance(columns.email.type, String)
    assert columns.email.type.length == 100
    assert isinstance(columns.created_at.type, DateTime)

    assert not SalesRep.__table__.foreign_keys


def test_product_model_matches_mysql_table():
    assert Product.__tablename__ == "sa_product"
    columns = Product.__table__.c

    assert isinstance(columns.id.type, BigInteger)
    assert isinstance(columns.sku_code.type, String)
    assert columns.sku_code.type.length == 50
    assert isinstance(columns.name.type, String)
    assert columns.name.type.length == 200
    assert isinstance(columns.category.type, String)
    assert columns.category.type.length == 50
    assert isinstance(columns.unit_price.type, Numeric)
    assert columns.unit_price.type.precision == 10
    assert columns.unit_price.type.scale == 2
    assert isinstance(columns.cost.type, Numeric)
    assert columns.cost.type.precision == 10
    assert columns.cost.type.scale == 2
    assert isinstance(columns.status.type, String)
    assert columns.status.type.length == 20
    assert isinstance(columns.created_at.type, DateTime)

    assert not Product.__table__.foreign_keys


def test_sales_order_model_matches_mysql_table():
    assert SalesOrder.__tablename__ == "sa_sales_order"
    columns = SalesOrder.__table__.c

    assert isinstance(columns.id.type, BigInteger)
    assert isinstance(columns.order_no.type, String)
    assert columns.order_no.type.length == 50
    assert isinstance(columns.rep_id.type, BigInteger)
    assert isinstance(columns.product_id.type, BigInteger)
    assert isinstance(columns.region_id.type, BigInteger)
    assert isinstance(columns.customer_name.type, String)
    assert columns.customer_name.type.length == 100
    assert isinstance(columns.quantity.type, Integer)
    assert isinstance(columns.unit_price.type, Numeric)
    assert columns.unit_price.type.precision == 10
    assert columns.unit_price.type.scale == 2
    assert isinstance(columns.amount.type, Numeric)
    assert columns.amount.type.precision == 12
    assert columns.amount.type.scale == 2
    assert isinstance(columns.cost.type, Numeric)
    assert columns.cost.type.precision == 12
    assert columns.cost.type.scale == 2
    assert isinstance(columns.profit.type, Numeric)
    assert columns.profit.type.precision == 12
    assert columns.profit.type.scale == 2
    assert isinstance(columns.status.type, String)
    assert columns.status.type.length == 20
    assert isinstance(columns.order_date.type, Date)
    assert isinstance(columns.created_at.type, DateTime)

    assert not SalesOrder.__table__.foreign_keys
