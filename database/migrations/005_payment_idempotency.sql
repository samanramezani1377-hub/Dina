-- Payment idempotency. A client retry must not create a second payment.
CREATE TABLE IF NOT EXISTS payment_idempotency (
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    payment_id BIGINT NOT NULL REFERENCES payments(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (organization_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_payment_idempotency_payment ON payment_idempotency(payment_id);
