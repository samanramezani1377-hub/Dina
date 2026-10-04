-- Dina product/compliance expansion: platform control plane + accounting extensions.
CREATE TABLE IF NOT EXISTS platform_admins (
 user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS plans (
 id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', price NUMERIC(20,4) NOT NULL DEFAULT 0 CHECK(price>=0),
 currency TEXT NOT NULL DEFAULT 'IRR', billing_period TEXT NOT NULL CHECK(billing_period IN ('month','quarter','year','lifetime')),
 trial_days INTEGER NOT NULL DEFAULT 0 CHECK(trial_days>=0), max_users INTEGER, max_products INTEGER,
 max_invoices INTEGER, max_warehouses INTEGER, max_storage_mb INTEGER, active BOOLEAN NOT NULL DEFAULT TRUE,
 features JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS plan_entitlements (
 plan_id BIGINT NOT NULL REFERENCES plans(id) ON DELETE CASCADE, feature TEXT NOT NULL,
 enabled BOOLEAN NOT NULL DEFAULT TRUE, limit_value BIGINT, PRIMARY KEY(plan_id,feature)
);
CREATE TABLE IF NOT EXISTS subscription_history (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 subscription_id BIGINT REFERENCES subscriptions(id) ON DELETE SET NULL, plan_id BIGINT REFERENCES plans(id),
 action TEXT NOT NULL, metadata JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS usage_counters (
 organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, metric TEXT NOT NULL,
 value BIGINT NOT NULL DEFAULT 0, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(organization_id,metric)
);
CREATE TABLE IF NOT EXISTS billing_invoices (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 invoice_no TEXT NOT NULL, plan_id BIGINT REFERENCES plans(id), amount NUMERIC(20,4) NOT NULL,
 currency TEXT NOT NULL DEFAULT 'IRR', status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('draft','open','paid','void','refunded')),
 issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), due_at TIMESTAMPTZ, paid_at TIMESTAMPTZ,
 UNIQUE(organization_id,invoice_no)
);
CREATE TABLE IF NOT EXISTS user_security_events (
 id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
 event_type TEXT NOT NULL, ip_address INET, metadata JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS password_reset_tokens (
 id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 token_hash TEXT UNIQUE NOT NULL, expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS email_verification_tokens (
 id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 token_hash TEXT UNIQUE NOT NULL, expires_at TIMESTAMPTZ NOT NULL, verified_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS accounting_parties (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('customer','supplier','both','person')), name TEXT NOT NULL,
 national_id TEXT, economic_code TEXT, phone TEXT, email TEXT, address TEXT,
 receivable_account_id BIGINT REFERENCES accounts(id), payable_account_id BIGINT REFERENCES accounts(id), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS expenses (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 party_id BIGINT REFERENCES accounting_parties(id), expense_account_id BIGINT REFERENCES accounts(id),
 cash_account_id BIGINT REFERENCES cash_accounts(id), amount NUMERIC(20,4) NOT NULL CHECK(amount>0),
 expense_date DATE NOT NULL, description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'posted',
 journal_entry_id BIGINT REFERENCES journal_entries(id), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS fixed_assets (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 name TEXT NOT NULL, acquisition_date DATE NOT NULL, cost NUMERIC(20,4) NOT NULL CHECK(cost>=0),
 useful_life_months INTEGER NOT NULL CHECK(useful_life_months>0), residual_value NUMERIC(20,4) NOT NULL DEFAULT 0,
 accumulated_depreciation NUMERIC(20,4) NOT NULL DEFAULT 0, asset_account_id BIGINT REFERENCES accounts(id),
 depreciation_account_id BIGINT REFERENCES accounts(id), expense_account_id BIGINT REFERENCES accounts(id), status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS cost_centers (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 code TEXT NOT NULL, name TEXT NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE, UNIQUE(organization_id,code)
);
CREATE TABLE IF NOT EXISTS attachments (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 entity_type TEXT NOT NULL, entity_id BIGINT NOT NULL, file_name TEXT NOT NULL, content_type TEXT NOT NULL,
 storage_key TEXT NOT NULL, size_bytes BIGINT NOT NULL CHECK(size_bytes>=0), sha256 TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS bank_reconciliations (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 cash_account_id BIGINT NOT NULL REFERENCES cash_accounts(id), statement_date DATE NOT NULL,
 statement_balance NUMERIC(20,4) NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','reconciled')),
 reconciled_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS bank_statement_lines (
 id BIGSERIAL PRIMARY KEY, reconciliation_id BIGINT NOT NULL REFERENCES bank_reconciliations(id) ON DELETE CASCADE,
 transaction_date DATE NOT NULL, amount NUMERIC(20,4) NOT NULL, description TEXT NOT NULL DEFAULT '',
 reference TEXT, matched_cash_transaction_id BIGINT REFERENCES cash_transactions(id), matched_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS tax_profiles (
 organization_id BIGINT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
 legal_name TEXT, national_id TEXT, economic_code TEXT, tax_number TEXT, fiscal_memory_id TEXT,
 taxpayer_system_enabled BOOLEAN NOT NULL DEFAULT FALSE, vat_enabled BOOLEAN NOT NULL DEFAULT TRUE,
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS tax_invoices (
 id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 sale_id BIGINT REFERENCES sales(id), invoice_type TEXT NOT NULL, tax_id TEXT, status TEXT NOT NULL DEFAULT 'draft',
 submitted_at TIMESTAMPTZ, response_code TEXT, response_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_platform_usage_org ON usage_counters(organization_id);
CREATE INDEX IF NOT EXISTS idx_billing_invoices_org ON billing_invoices(organization_id,issued_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_user ON user_security_events(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attachments_entity ON attachments(organization_id,entity_type,entity_id);
