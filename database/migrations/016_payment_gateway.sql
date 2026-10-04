-- Gateway-specific metadata kept outside the accounting schema.
-- ZarinPal uses payment_attempts.provider_reference for Authority and metadata
-- for gateway response details; no gateway secret is stored in PostgreSQL.
CREATE INDEX IF NOT EXISTS idx_payment_attempts_provider_status
    ON payment_attempts(provider, status, created_at DESC);
