CREATE TABLE IF NOT EXISTS rate_limit_buckets (
 bucket_key TEXT PRIMARY KEY,
 window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 request_count INTEGER NOT NULL DEFAULT 0
);
