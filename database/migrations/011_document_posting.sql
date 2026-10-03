-- Normalize the status introduced by the initial sales/purchases schema before
-- adding posting semantics. This is safe for databases that already ran 010.
ALTER TABLE sales DROP CONSTRAINT IF EXISTS sales_status_check;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_status_check;
ALTER TABLE sales ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'draft';
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'draft';
UPDATE sales SET status='draft' WHERE status NOT IN ('draft','posted','cancelled');
UPDATE purchases SET status='draft' WHERE status NOT IN ('draft','posted','cancelled');
ALTER TABLE sales ALTER COLUMN status SET DEFAULT 'draft';
ALTER TABLE purchases ALTER COLUMN status SET DEFAULT 'draft';
ALTER TABLE sales ADD CONSTRAINT sales_status_check CHECK (status IN ('draft','posted','cancelled'));
ALTER TABLE purchases ADD CONSTRAINT purchases_status_check CHECK (status IN ('draft','posted','cancelled'));
ALTER TABLE sales ADD COLUMN IF NOT EXISTS journal_entry_id BIGINT REFERENCES journal_entries(id);
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS journal_entry_id BIGINT REFERENCES journal_entries(id);
CREATE UNIQUE INDEX IF NOT EXISTS sales_org_invoice_no_uq ON sales(organization_id, invoice_no);
CREATE UNIQUE INDEX IF NOT EXISTS purchases_org_invoice_no_uq ON purchases(organization_id, invoice_no);
