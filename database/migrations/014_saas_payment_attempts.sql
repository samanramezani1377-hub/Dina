-- Idempotent SaaS payment lifecycle and webhook/event audit.
CREATE TABLE IF NOT EXISTS payment_attempts (
 id BIGSERIAL PRIMARY KEY,
 organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 provider TEXT NOT NULL,
 idempotency_key TEXT NOT NULL,
 provider_reference TEXT,
 amount NUMERIC(20,4) NOT NULL CHECK (amount > 0),
 currency TEXT NOT NULL DEFAULT 'IRR',
 status TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created','pending','succeeded','failed','cancelled')),
 subscription_id BIGINT REFERENCES subscriptions(id) ON DELETE SET NULL,
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE (organization_id, provider, idempotency_key),
 UNIQUE (provider, provider_reference)
);
CREATE INDEX IF NOT EXISTS idx_payment_attempts_org ON payment_attempts(organization_id, created_at DESC);
CREATE TABLE IF NOT EXISTS subscription_events (
 id BIGSERIAL PRIMARY KEY,
 organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
 provider TEXT NOT NULL,
 event_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 payload JSONB NOT NULL DEFAULT '{}'::jsonb,
 processed_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(provider, event_id)
);
CREATE INDEX IF NOT EXISTS idx_subscription_events_org ON subscription_events(organization_id, created_at DESC);
