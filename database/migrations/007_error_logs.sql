-- Centralized application error log. Sensitive request data is never stored.
CREATE TABLE IF NOT EXISTS error_logs (
    id BIGSERIAL PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL DEFAULT 'error' CHECK (level IN ('warning','error','critical')),
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    user_id BIGINT NULL,
    organization_id BIGINT NULL,
    ip_address INET NULL,
    user_agent TEXT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    traceback TEXT NULL,
    resolved_at TIMESTAMPTZ NULL,
    resolved_by BIGINT NULL
);
CREATE INDEX IF NOT EXISTS idx_error_logs_occurred_at ON error_logs(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_logs_correlation ON error_logs(correlation_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_code ON error_logs(code);
CREATE INDEX IF NOT EXISTS idx_error_logs_org ON error_logs(organization_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_unresolved ON error_logs(resolved_at) WHERE resolved_at IS NULL;
