-- Inventory valuation and document warehouse/accounting links.
ALTER TABLE products ADD COLUMN IF NOT EXISTS inventory_account_id BIGINT REFERENCES accounts(id);
ALTER TABLE products ADD COLUMN IF NOT EXISTS cogs_account_id BIGINT REFERENCES accounts(id);
ALTER TABLE products ADD COLUMN IF NOT EXISTS revenue_account_id BIGINT REFERENCES accounts(id);
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(20,4) NOT NULL DEFAULT 0;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS warehouse_id BIGINT REFERENCES warehouses(id);
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS warehouse_id BIGINT REFERENCES warehouses(id);
ALTER TABLE cash_transactions ADD COLUMN IF NOT EXISTS counter_account_id BIGINT REFERENCES accounts(id);
ALTER TABLE checks ADD COLUMN IF NOT EXISTS journal_entry_id BIGINT REFERENCES journal_entries(id);
CREATE INDEX IF NOT EXISTS idx_stock_org_product_wh ON stock_movements(organization_id,product_id,warehouse_id);
CREATE INDEX IF NOT EXISTS idx_sales_org_warehouse ON sales(organization_id,warehouse_id);
CREATE INDEX IF NOT EXISTS idx_purchases_org_warehouse ON purchases(organization_id,warehouse_id);
