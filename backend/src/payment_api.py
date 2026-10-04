from __future__ import annotations
from decimal import Decimal
from typing import Protocol, Any
import hmac
import os
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from .errors import ApiError, ErrorCode
from .identity import Caller
from .operations_api import accounting_caller, member_caller

router = APIRouter(prefix="/api/v1/organizations", tags=["payments"])

class PaymentProvider(Protocol):
    name: str
    def create_payment(self, amount: Decimal, currency: str, reference: str) -> dict[str, Any]: ...

class PaymentAttemptInput(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="IRR", min_length=3, max_length=10)
    subscription_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class PaymentWebhookInput(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    event_id: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=100)
    organization_id: int | None = None
    payment_attempt_id: int | None = None
    status: str | None = None
    provider_reference: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

def _db(request: Request) -> str:
    return request.app.state.settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

def _json(value):
    if isinstance(value, Decimal): return str(value)
    if hasattr(value, "isoformat"): return value.isoformat()
    if isinstance(value, dict): return {k: _json(v) for k, v in value.items()}
    if isinstance(value, list): return [_json(v) for v in value]
    return value

@router.post("/{organization_id}/payments/attempts", status_code=201)
def create_payment_attempt(organization_id: int, payload: PaymentAttemptInput, request: Request,
                           caller: Caller = Depends(accounting_caller)):
    key = request.headers.get("Idempotency-Key")
    if not key: raise ApiError(ErrorCode.VALIDATION_ERROR, "Idempotency-Key is required")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        existing = cn.execute("SELECT * FROM payment_attempts WHERE organization_id=%s AND provider=%s AND idempotency_key=%s",
                              (organization_id, payload.provider, key)).fetchone()
        if existing: return _json(dict(existing))
        if payload.subscription_id is not None:
            subscription = cn.execute("SELECT id FROM subscriptions WHERE id=%s AND organization_id=%s",
                                     (payload.subscription_id, organization_id)).fetchone()
            if not subscription:
                raise ApiError(ErrorCode.NOT_FOUND, "subscription not found")
        try:
            row = cn.execute("""INSERT INTO payment_attempts
                (organization_id,provider,idempotency_key,amount,currency,subscription_id,metadata)
                VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (organization_id, payload.provider, key, payload.amount, payload.currency,
                 payload.subscription_id, psycopg.types.json.Jsonb(payload.metadata))).fetchone()
        except psycopg.errors.UniqueViolation:
            row = cn.execute("SELECT * FROM payment_attempts WHERE organization_id=%s AND provider=%s AND idempotency_key=%s",
                             (organization_id, payload.provider, key)).fetchone()
    return _json(dict(row))

@router.get("/{organization_id}/payments/attempts")
def list_payment_attempts(organization_id: int, request: Request,
                           caller: Caller = Depends(member_caller)):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        rows = cn.execute("""SELECT id,provider,idempotency_key,provider_reference,amount,currency,
            status,subscription_id,metadata,created_at,updated_at FROM payment_attempts
            WHERE organization_id=%s ORDER BY id DESC LIMIT 100""", (organization_id,)).fetchall()
    return {"items": _json([dict(x) for x in rows])}

@router.post("/{organization_id}/payments/webhook", status_code=202)
def payment_webhook(organization_id: int, payload: PaymentWebhookInput, request: Request):
    configured_secret = os.environ.get("PAYMENT_WEBHOOK_SECRET", "").strip()
    supplied_secret = request.headers.get("X-Payment-Webhook-Secret", "")
    if not configured_secret or not hmac.compare_digest(supplied_secret, configured_secret):
        raise ApiError(ErrorCode.PERMISSION_DENIED, "invalid payment webhook signature")
    if payload.organization_id not in (None, organization_id):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "organization mismatch")
    allowed = {"created","pending","succeeded","failed","cancelled"}
    if payload.status is not None and payload.status not in allowed:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "invalid payment status")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        event = cn.execute("""INSERT INTO subscription_events
            (organization_id,provider,event_id,event_type,payload,processed_at)
            VALUES(%s,%s,%s,%s,%s,NOW())
            ON CONFLICT(provider,event_id) DO NOTHING RETURNING id""",
            (organization_id, payload.provider, payload.event_id, payload.event_type,
             psycopg.types.json.Jsonb(payload.payload))).fetchone()
        if not event: return {"accepted": True, "duplicate": True}
        if payload.payment_attempt_id is not None:
            attempt = cn.execute("SELECT id FROM payment_attempts WHERE id=%s AND organization_id=%s FOR UPDATE",
                                 (payload.payment_attempt_id, organization_id)).fetchone()
            if not attempt: raise ApiError(ErrorCode.NOT_FOUND, "payment attempt not found")
            if payload.status is not None:
                transitions = {
                    "created": {"pending", "failed", "cancelled"},
                    "pending": {"succeeded", "failed", "cancelled"},
                    "succeeded": set(),
                    "failed": set(),
                    "cancelled": set(),
                }
                current = attempt["status"]
                if payload.status != current and payload.status not in transitions[current]:
                    raise ApiError(ErrorCode.VALIDATION_ERROR, "invalid payment status transition")
                cn.execute("""UPDATE payment_attempts SET status=%s,
                    provider_reference=COALESCE(%s,provider_reference),updated_at=NOW() WHERE id=%s""",
                    (payload.status, payload.provider_reference, payload.payment_attempt_id))
    return {"accepted": True, "duplicate": False, "event_id": payload.event_id}
