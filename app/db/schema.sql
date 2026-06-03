CREATE TABLE IF NOT EXISTS sales_region (
    id INTEGER PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    code VARCHAR(32) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS sales_rep (
    id INTEGER PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    region_id INTEGER NOT NULL REFERENCES sales_region(id)
);

CREATE TABLE IF NOT EXISTS product (
    id INTEGER PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    category VARCHAR(64) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS sales_order (
    id INTEGER PRIMARY KEY,
    order_no VARCHAR(64) NOT NULL UNIQUE,
    region_id INTEGER NOT NULL REFERENCES sales_region(id),
    sales_rep_id INTEGER NOT NULL REFERENCES sales_rep(id),
    product_id INTEGER NOT NULL REFERENCES product(id),
    order_date DATE NOT NULL,
    quantity INTEGER NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_sales_order_order_date
    ON sales_order(order_date);

CREATE INDEX IF NOT EXISTS ix_sales_order_region_date
    ON sales_order(region_id, order_date);

CREATE INDEX IF NOT EXISTS ix_sales_order_rep_date
    ON sales_order(sales_rep_id, order_date);
