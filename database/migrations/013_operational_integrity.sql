-- Complete schema required by posted sales/purchases and inventory valuation.
ALTER TABLE sales ADD COLUMN IF NOT EXISTS warehouse_id BIGINT REFERENCES warehouses(id);
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS warehouse_id BIGINT REFERENCES warehouses(id);
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(20,4) NOT NULL DEFAULT 0 CHECK(unit_cost >= 0);
CREATE INDEX IF NOT EXISTS idx_sales_org_warehouse ON sales(organization_id, warehouse_id);
CREATE INDEX IF NOT EXISTS idx_purchases_org_warehouse ON purchases(organization_id, warehouse_id);
