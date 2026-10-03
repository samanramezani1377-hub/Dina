"""Persistent centralized error logging for Dina.

The error center deliberately stores diagnostic context without request bodies,
authorization headers, cookies, passwords or arbitrary secrets.
"""
from __future__ import annotations
import json
import logging
import traceback as tb
from datetime import datetime, timezone
from typing import Any
import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger("dina.error_center")

_SENSITIVE = {"authorization","cookie","set-cookie","password","passwd","secret","token","access_token","refresh_token","api_key","key","credit_card","card_number","cvv"}

def redact(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "[redacted-depth]"
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = str(k).lower().replace("-", "_")
            if key in _SENSITIVE or any(s in key for s in _SENSITIVE if len(s) > 4):
                out[str(k)] = "[REDACTED]"
            else:
                out[str(k)] = redact(v, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v, depth + 1) for v in value[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)

def _connect(database_url: str):
    return psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://", 1), row_factory=dict_row)

def record_error(database_url: str, *, correlation_id: str, code: str, message: str,
                 http_status: int, method: str, path: str, user_id: int | None = None,
                 organization_id: int | None = None, ip_address: str | None = None,
                 user_agent: str | None = None, details: dict[str, Any] | None = None,
                 exception: BaseException | None = None, level: str = "error") -> None:
    """Best-effort persistence; an error logger must never create a second error."""
    try:
        trace = None
        if exception is not None:
            trace = "".join(tb.format_exception(type(exception), exception, exception.__traceback__))
            trace = trace[-30000:]
        with _connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO error_logs
                    (correlation_id, level, code, message, http_status, method, path,
                     user_id, organization_id, ip_address, user_agent, details, traceback)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (correlation_id, level, code, message[:2000], http_status, method[:16],
                     path[:1000], user_id, organization_id, ip_address,
                     (user_agent or "")[:1000] or None,
                     json.dumps(redact(details or {}), ensure_ascii=False),
                     trace),
                )
            conn.commit()
    except Exception:
        logger.exception("failed to persist error log correlation_id=%s", correlation_id)

def list_errors(database_url: str, *, limit: int = 100, offset: int = 0,
                code: str | None = None, unresolved_only: bool = False) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500)); offset = max(0, offset)
    clauses=[]; params=[]
    if code: clauses.append("code=%s"); params.append(code)
    if unresolved_only: clauses.append("resolved_at IS NULL")
    where=(" WHERE "+" AND ".join(clauses)) if clauses else ""
    with _connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT id, correlation_id, occurred_at, level, code, message,
                http_status, method, path, user_id, organization_id, ip_address::text AS ip_address,
                user_agent, details, traceback, resolved_at, resolved_by
                FROM error_logs{where} ORDER BY occurred_at DESC LIMIT %s OFFSET %s""",
                (*params, limit, offset))
            return list(cur.fetchall())

def resolve_error(database_url: str, error_id: int, user_id: int) -> bool:
    with _connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE error_logs SET resolved_at=NOW(), resolved_by=%s WHERE id=%s AND resolved_at IS NULL",
                        (user_id, error_id))
            return cur.rowcount == 1
