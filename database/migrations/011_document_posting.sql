ALTER TABLE sales ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted','cancelled'));
ALTER TABLE sales ADD COLUMN IF NOT EXISTS journal_entry_id BIGINT REFERENCES journal_entries(id);
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted','cancelled'));
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS journal_entry_id BIGINT REFERENCES journal_entries(id);
CREATE UNIQUE INDEX IF NOT EXISTS sales_org_invoice_no_uq ON sales(organization_id, invoice_no);
CREATE UNIQUE INDEX IF NOT EXISTS purchases_org_invoice_no_uq ON purchases(organization_id, invoice_no);
