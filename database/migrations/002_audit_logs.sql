-- Dina audit trail, PostgreSQL.
--
-- Append-only by construction:
--   * UPDATE and DELETE are revoked from the application role.
--   * A BEFORE UPDATE OR DELETE trigger rejects them even for the table owner,
--     so an application bug cannot rewrite history.
-- The only permitted DML is INSERT.
--
-- organization_id is nullable on purpose: authentication events (a failed
-- login for an unknown email) happen before any tenant is known.

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT,
    user_id BIGINT,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    correlation_id TEXT,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes cover every lookup the query API performs: tenant scoping, per user,
-- per action and a chronological page.
CREATE INDEX IF NOT EXISTS idx_audit_logs_org ON audit_logs(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_occurred_at ON audit_logs(occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_org_occurred
    ON audit_logs(organization_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_metadata ON audit_logs USING GIN (metadata);

-- Foreign keys are attached only when the referenced tables exist, so this
-- migration is safe to run before the auth/organization migrations.
DO $$
BEGIN
    IF to_regclass('organizations') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'fk_audit_logs_organization'
       ) THEN
        ALTER TABLE audit_logs
            ADD CONSTRAINT fk_audit_logs_organization
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL;
    END IF;
    IF to_regclass('users') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'fk_audit_logs_user'
       ) THEN
        ALTER TABLE audit_logs
            ADD CONSTRAINT fk_audit_logs_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END
$$;

-- Append-only enforcement. The audit trail may only grow.
CREATE OR REPLACE FUNCTION audit_logs_reject_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: % is not permitted', TG_OP
        USING ERRCODE = '42501';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs;
CREATE TRIGGER trg_audit_logs_append_only
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_reject_mutation();

-- Application role must not be able to rewrite or erase history. Set the role
-- name to your deployment's application role before running this migration;
-- with no role named dina_app the REVOKE is a harmless no-op.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dina_app') THEN
        REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM dina_app;
    END IF;
END
$$;

COMMENT ON TABLE audit_logs IS
    'Append-only audit trail for sensitive operations. No UPDATE or DELETE path exists, in the application or the database.';
