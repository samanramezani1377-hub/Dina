from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request

from .errors import ApiError, ErrorCode

WINDOW_SECONDS = 600
MAX_AUTH_ATTEMPTS = 20


def _db(request: Request) -> str:
    return request.app.state.settings.database_url.replace(
        "postgresql+psycopg://", "postgresql://", 1
    )


def enforce_auth_rate_limit(request: Request) -> None:
    if request.app.state.settings.is_test:
        return
    import psycopg

    ip = request.client.host if request.client else "unknown"
    key = f"auth:{request.url.path}:{ip}"
    with psycopg.connect(_db(request)) as cn:
        cn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
        row = cn.execute(
            "SELECT window_started_at,request_count FROM rate_limit_buckets WHERE bucket_key=%s FOR UPDATE",
            (key,),
        ).fetchone()
        now = datetime.now(timezone.utc)
        if row is None:
            cn.execute(
                """INSERT INTO rate_limit_buckets(bucket_key,window_started_at,request_count)
                   VALUES(%s,%s,1)""",
                (key, now),
            )
            return
        started, count = row
        elapsed = (now - started).total_seconds()
        if elapsed >= WINDOW_SECONDS:
            cn.execute(
                """UPDATE rate_limit_buckets
                   SET window_started_at=%s,request_count=1 WHERE bucket_key=%s""",
                (now, key),
            )
            return
        if count >= MAX_AUTH_ATTEMPTS:
            retry = max(1, int(WINDOW_SECONDS - elapsed))
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                "too many authentication attempts",
                {"retry_after_seconds": retry},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        cn.execute(
            "UPDATE rate_limit_buckets SET request_count=request_count+1 WHERE bucket_key=%s",
            (key,),
        )
