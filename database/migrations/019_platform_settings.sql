CREATE TABLE IF NOT EXISTS platform_settings (
 id BIGSERIAL PRIMARY KEY,
 setting_key TEXT NOT NULL UNIQUE,
 setting_value TEXT NOT NULL,
 is_secret BOOLEAN NOT NULL DEFAULT TRUE,
 updated_by BIGINT REFERENCES users(id),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_platform_settings_updated ON platform_settings(updated_at DESC);
