import re
from pathlib import Path


DATA_SQL = Path("app/db/data.sql")


def test_data_sql_contains_complete_reference_seed_data():
    sql = DATA_SQL.read_text(encoding="utf-8")

    assert _count_insert_rows(sql, "sa_sales_region") == 4
    assert _count_insert_rows(sql, "sa_sales_rep") == 13
    assert _count_insert_rows(sql, "sa_product") == 20
    assert len(re.findall(r"^\('ORD-", sql, flags=re.MULTILINE)) == 69


def test_data_sql_keeps_reference_anomaly_points():
    sql = DATA_SQL.read_text(encoding="utf-8")

    assert "华北区（region_id=3）近 14 天内无订单" in sql
    assert "SKU-8821（product_id=6）近 30 天内零销售" in sql
    assert "张磊（rep_id=8）近 60 天仅1单" in sql
    assert "王芳（rep_id=3）历史退单率异常高" in sql
    assert "ORD-B06-006" in sql
    assert "ORD-B06-008" in sql
    assert "ORD-B07-007" in sql


def _count_insert_rows(sql: str, table_name: str) -> int:
    match = re.search(
        rf"INSERT\s+INTO\s+{table_name}\s*\(.*?\)\s*VALUES\s*(.*?);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, f"Missing INSERT block for {table_name}"
    return len(re.findall(r"^\s*\(", match.group(1), flags=re.MULTILINE))
