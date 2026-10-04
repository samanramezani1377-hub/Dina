-- Release/compliance hardening: tax outbox, reconciliation, depreciation, and observability.
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS organization_id BIGINT;
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS sale_id BIGINT;
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS invoice_type TEXT NOT NULL DEFAULT 'sale';
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS tax_id TEXT;
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'draft';
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS response_code TEXT;
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS response_payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS submitted_by BIGINT REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_tax_invoices_org_status ON tax_invoices(organization_id,status,created_at DESC);

CREATE TABLE IF NOT EXISTS tax_submission_attempts (
 id BIGSERIAL PRIMARY KEY,
 tax_invoice_id BIGINT NOT NULL REFERENCES tax_invoices(id) ON DELETE CASCADE,
 idempotency_key TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','submitted','accepted','rejected','failed')),
 provider_reference TEXT,
 request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
 response_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
 error_message TEXT,
 attempted_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(tax_invoice_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_tax_attempts_status ON tax_submission_attempts(status,updated_at);

CREATE TABLE IF NOT EXISTS depreciation_runs (
 id BIGSERIAL PRIMARY KEY,
 organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 period_start DATE NOT NULL,
 period_end DATE NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','posted','cancelled')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(organization_id,period_start,period_end)
);
CREATE TABLE IF NOT EXISTS asset_depreciation_entries (
 id BIGSERIAL PRIMARY KEY,
 organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 asset_id BIGINT NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
 period_start DATE NOT NULL,
 period_end DATE NOT NULL,
 amount NUMERIC(20,4) NOT NULL CHECK(amount>=0),
 journal_entry_id BIGINT REFERENCES journal_entries(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(asset_id,period_start,period_end)
);
CREATE INDEX IF NOT EXISTS idx_asset_depreciation_org_period ON asset_depreciation_entries(organization_id,period_end);

ALTER TABLE bank_statement_lines ADD COLUMN IF NOT EXISTS matched_amount NUMERIC(20,4);
ALTER TABLE bank_statement_lines ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'unmatched'
 CHECK(status IN ('unmatched','matched','ignored'));
CREATE INDEX IF NOT EXISTS idx_bank_statement_lines_status ON bank_statement_lines(reconciliation_id,status);
