CREATE TABLE IF NOT EXISTS sales (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 customer_id BIGINT NOT NULL, invoice_no TEXT NOT NULL, issue_date DATE NOT NULL,
 due_date DATE, subtotal NUMERIC(20,4) NOT NULL DEFAULT 0, discount NUMERIC(20,4) NOT NULL DEFAULT 0,
 tax NUMERIC(20,4) NOT NULL DEFAULT 0, total NUMERIC(20,4) NOT NULL CHECK(total >= 0),
 status TEXT NOT NULL DEFAULT 'issued' CHECK(status IN ('draft','issued','paid','cancelled')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(organization_id,invoice_no)
);
CREATE TABLE IF NOT EXISTS sale_lines (
 id BIGSERIAL PRIMARY KEY, sale_id BIGINT NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
 product_id BIGINT REFERENCES products(id), description TEXT NOT NULL, quantity NUMERIC(20,4) NOT NULL CHECK(quantity > 0),
 unit_price NUMERIC(20,4) NOT NULL CHECK(unit_price >= 0), discount NUMERIC(20,4) NOT NULL DEFAULT 0,
 tax NUMERIC(20,4) NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS purchases (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 supplier_id BIGINT NOT NULL, invoice_no TEXT NOT NULL, issue_date DATE NOT NULL,
 due_date DATE, subtotal NUMERIC(20,4) NOT NULL DEFAULT 0, discount NUMERIC(20,4) NOT NULL DEFAULT 0,
 tax NUMERIC(20,4) NOT NULL DEFAULT 0, total NUMERIC(20,4) NOT NULL CHECK(total >= 0),
 status TEXT NOT NULL DEFAULT 'issued' CHECK(status IN ('draft','issued','paid','cancelled')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(organization_id,invoice_no)
);
CREATE TABLE IF NOT EXISTS purchase_lines (
 id BIGSERIAL PRIMARY KEY, purchase_id BIGINT NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
 product_id BIGINT REFERENCES products(id), description TEXT NOT NULL, quantity NUMERIC(20,4) NOT NULL CHECK(quantity > 0),
 unit_price NUMERIC(20,4) NOT NULL CHECK(unit_price >= 0), discount NUMERIC(20,4) NOT NULL DEFAULT 0,
 tax NUMERIC(20,4) NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sales_org_date ON sales(organization_id,issue_date);
CREATE INDEX IF NOT EXISTS idx_purchases_org_date ON purchases(organization_id,issue_date);
