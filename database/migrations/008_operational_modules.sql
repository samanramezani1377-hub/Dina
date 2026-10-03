-- Dina operational accounting modules: fiscal years, parties, products, warehouses, treasury and checks.
CREATE TABLE IF NOT EXISTS fiscal_years (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 name TEXT NOT NULL, starts_on DATE NOT NULL, ends_on DATE NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
 UNIQUE(organization_id,name), CHECK(ends_on >= starts_on)
);
CREATE INDEX IF NOT EXISTS idx_fiscal_years_org ON fiscal_years(organization_id);

CREATE TABLE IF NOT EXISTS suppliers (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 name TEXT NOT NULL, email TEXT, phone TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_suppliers_org ON suppliers(organization_id);

CREATE TABLE IF NOT EXISTS products (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 sku TEXT, name TEXT NOT NULL, unit TEXT NOT NULL DEFAULT 'عدد',
 purchase_price NUMERIC(20,4) NOT NULL DEFAULT 0 CHECK(purchase_price >= 0),
 sale_price NUMERIC(20,4) NOT NULL DEFAULT 0 CHECK(sale_price >= 0),
 track_inventory BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(organization_id,sku)
);
CREATE INDEX IF NOT EXISTS idx_products_org ON products(organization_id);

CREATE TABLE IF NOT EXISTS warehouses (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(organization_id,name)
);

CREATE TABLE IF NOT EXISTS stock_movements (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 warehouse_id BIGINT NOT NULL REFERENCES warehouses(id), product_id BIGINT NOT NULL REFERENCES products(id),
 quantity NUMERIC(20,4) NOT NULL CHECK(quantity <> 0), movement_type TEXT NOT NULL,
 reference TEXT, movement_date DATE NOT NULL DEFAULT CURRENT_DATE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CHECK(movement_type IN ('receipt','issue','transfer_in','transfer_out','adjustment'))
);
CREATE INDEX IF NOT EXISTS idx_stock_org_product ON stock_movements(organization_id,product_id);
CREATE INDEX IF NOT EXISTS idx_stock_org_warehouse ON stock_movements(organization_id,warehouse_id);

CREATE TABLE IF NOT EXISTS cash_accounts (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('cash','bank')),
 account_number TEXT, opening_balance NUMERIC(20,4) NOT NULL DEFAULT 0,
 UNIQUE(organization_id,name)
);

CREATE TABLE IF NOT EXISTS cash_transactions (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 cash_account_id BIGINT NOT NULL REFERENCES cash_accounts(id),
 amount NUMERIC(20,4) NOT NULL CHECK(amount > 0), direction TEXT NOT NULL CHECK(direction IN ('in','out')),
 description TEXT NOT NULL DEFAULT '', reference TEXT, transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cash_tx_org ON cash_transactions(organization_id,cash_account_id);

CREATE TABLE IF NOT EXISTS checks (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id),
 party_name TEXT NOT NULL, amount NUMERIC(20,4) NOT NULL CHECK(amount > 0),
 due_date DATE NOT NULL, direction TEXT NOT NULL CHECK(direction IN ('received','issued')),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','deposited','cleared','bounced','cancelled')),
 bank_name TEXT, check_number TEXT, notes TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_checks_org_status ON checks(organization_id,status);
