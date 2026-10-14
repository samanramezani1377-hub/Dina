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
from .zarinpal import ZarinPalProvider

router = APIRouter(prefix="/api/v1/organizations", tags=["payments"])
public_router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


class PaymentProvider(Protocol):
    name: str

    def create_payment(
        self,
        amount: Decimal,
        currency: str,
        reference: str,
        organization_id: int,
        payment_attempt_id: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]: ...

    def verify(self, authority: str, amount: Decimal, currency: str) -> dict[str, Any]: ...


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
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json(v) for v in value]
    return value


def _provider(name: str, request: Request) -> PaymentProvider:
    normalized = name.strip().lower()
    if normalized == "zarinpal":
        from types import SimpleNamespace
        from .platform_settings_api import read_setting_value

        settings = request.app.state.settings
        merchant_id = read_setting_value("zarinpal_merchant_id")
        callback_url = read_setting_value("zarinpal_callback_url")
        sandbox_value = read_setting_value("zarinpal_sandbox")
        if sandbox_value is None:
            sandbox = settings.zarinpal_sandbox
        elif sandbox_value.strip().lower() in {"1", "true", "yes", "on"}:
            sandbox = True
        elif sandbox_value.strip().lower() in {"0", "false", "no", "off"}:
            sandbox = False
        else:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "invalid platform setting: zarinpal_sandbox")
        effective_settings = SimpleNamespace(
            zarinpal_merchant_id=merchant_id if merchant_id is not None else settings.zarinpal_merchant_id,
            zarinpal_callback_url=callback_url if callback_url is not None else settings.zarinpal_callback_url,
            zarinpal_sandbox=sandbox,
            zarinpal_timeout_seconds=settings.zarinpal_timeout_seconds,
        )
        return ZarinPalProvider(effective_settings)
    raise ApiError(ErrorCode.VALIDATION_ERROR, f"unsupported payment provider: {name}")


def _mark_attempt(
    request: Request,
    payment_attempt_id: int,
    *,
    status: str,
    provider_reference: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        row = cn.execute(
            "SELECT * FROM payment_attempts WHERE id=%s FOR UPDATE",
            (payment_attempt_id,),
        ).fetchone()
        if not row:
            raise ApiError(ErrorCode.NOT_FOUND, "payment attempt not found")
        transitions = {
            "created": {"pending", "failed", "cancelled"},
            "pending": {"succeeded", "failed", "cancelled"},
            "succeeded": set(),
            "failed": set(),
            "cancelled": set(),
        }
        current = row["status"]
        if status != current and status not in transitions[current]:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "invalid payment status transition")
        if metadata:
            merged = dict(row["metadata"] or {})
            merged.update(metadata)
            row = cn.execute(
                """UPDATE payment_attempts SET status=%s,
                   provider_reference=COALESCE(%s,provider_reference),
                   metadata=%s,updated_at=NOW() WHERE id=%s RETURNING *""",
                (status, provider_reference, psycopg.types.json.Jsonb(merged), payment_attempt_id),
            ).fetchone()
        else:
            row = cn.execute(
                """UPDATE payment_attempts SET status=%s,
                   provider_reference=COALESCE(%s,provider_reference),
                   updated_at=NOW() WHERE id=%s RETURNING *""",
                (status, provider_reference, payment_attempt_id),
            ).fetchone()
    return dict(row)


def _complete_verified_attempt(
    request: Request,
    payment_attempt_id: int,
    organization_id: int,
    authority: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Atomically mark a verified gateway payment and activate its subscription."""
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        attempt = cn.execute(
            """SELECT * FROM payment_attempts
               WHERE id=%s AND organization_id=%s AND provider='zarinpal'
               FOR UPDATE""",
            (payment_attempt_id, organization_id),
        ).fetchone()
        if not attempt:
            raise ApiError(ErrorCode.NOT_FOUND, "payment attempt not found")
        if attempt["status"] == "succeeded":
            return dict(attempt)
        if attempt["status"] not in {"created", "pending"}:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "payment is no longer eligible for verification")
        if attempt["provider_reference"] and attempt["provider_reference"] != authority:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "ZarinPal authority mismatch")

        merged = dict(attempt["metadata"] or {})
        merged.update(metadata)
        updated = cn.execute(
            """UPDATE payment_attempts
               SET status='succeeded', provider_reference=%s, metadata=%s, updated_at=NOW()
               WHERE id=%s AND organization_id=%s
               RETURNING *""",
            (authority, psycopg.types.json.Jsonb(merged), payment_attempt_id, organization_id),
        ).fetchone()
        subscription_id = attempt["subscription_id"]
        if subscription_id is not None:
            subscription = cn.execute(
                """SELECT id FROM subscriptions
                   WHERE id=%s AND organization_id=%s FOR UPDATE""",
                (subscription_id, organization_id),
            ).fetchone()
            if not subscription:
                raise ApiError(ErrorCode.VALIDATION_ERROR, "payment subscription no longer exists")
            cn.execute(
                """UPDATE subscriptions SET status='active'
                   WHERE id=%s AND organization_id=%s""",
                (subscription_id, organization_id),
            )
        return dict(updated)


@router.post("/{organization_id}/payments/attempts", status_code=201)
def create_payment_attempt(
    organization_id: int,
    payload: PaymentAttemptInput,
    request: Request,
    caller: Caller = Depends(accounting_caller),
):
    key = request.headers.get("Idempotency-Key")
    if not key:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "Idempotency-Key is required")
    provider_name = payload.provider.strip().lower()
    import psycopg
    from psycopg.rows import dict_row
    if provider_name != "zarinpal":
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"unsupported payment provider: {provider_name}")

    currency = payload.currency.strip().upper()
    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        if payload.subscription_id is not None:
            subscription = cn.execute(
                "SELECT id FROM subscriptions WHERE id=%s AND organization_id=%s FOR UPDATE",
                (payload.subscription_id, organization_id),
            ).fetchone()
            if not subscription:
                raise ApiError(ErrorCode.NOT_FOUND, "subscription not found")
        row = cn.execute(
            """INSERT INTO payment_attempts
               (organization_id,provider,idempotency_key,amount,currency,subscription_id,metadata)
               VALUES(%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (organization_id,provider,idempotency_key) DO NOTHING
               RETURNING *""",
            (
                organization_id, provider_name, key, payload.amount, currency,
                payload.subscription_id, psycopg.types.json.Jsonb(payload.metadata),
            ),
        ).fetchone()
        created_now = row is not None
        if row is None:
            row = cn.execute(
                """SELECT * FROM payment_attempts
                   WHERE organization_id=%s AND provider=%s AND idempotency_key=%s
                   FOR UPDATE""",
                (organization_id, provider_name, key),
            ).fetchone()
            if row is None:
                raise ApiError(ErrorCode.VALIDATION_ERROR, "payment idempotency conflict; retry the request")
            same_request = (
                Decimal(str(row["amount"])) == payload.amount
                and str(row["currency"]).upper() == currency
                and row["subscription_id"] == payload.subscription_id
            )
            if not same_request:
                raise ApiError(
                    ErrorCode.VALIDATION_ERROR,
                    "Idempotency-Key was already used with different payment details",
                    {"payment_attempt_id": row["id"]},
                )
            # A replay must never create a second gateway payment. Return the
            # original result (including its original payment URL when present).
            existing = dict(row)
            payment_url = (existing.get("metadata") or {}).get("payment_url")
            return _json({**existing, **({"payment_url": payment_url} if payment_url else {})})
        attempt = dict(row)

    try:
        provider = _provider(provider_name, request)
        result = provider.create_payment(
            payload.amount,
            payload.currency,
            str(attempt["id"]),
            organization_id,
            int(attempt["id"]),
            payload.metadata,
        )
        attempt = _mark_attempt(
            request,
            int(attempt["id"]),
            status="pending",
            provider_reference=result["authority"],
            metadata={"payment_url": result["payment_url"], "gateway_code": result["gateway_code"]},
        )
        return _json({**attempt, "payment_url": result["payment_url"]})
    except ApiError as exc:
        _mark_attempt(request, int(attempt["id"]), status="failed", metadata={"gateway_error": exc.message})
        raise


@router.get("/{organization_id}/payments/summary")
def payment_summary(
    organization_id: int,
    request: Request,
    caller: Caller = Depends(accounting_caller),
):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        summary = cn.execute(
            """SELECT status, COUNT(*) AS count, COALESCE(SUM(amount),0) AS amount
               FROM payment_attempts WHERE organization_id=%s
               GROUP BY status ORDER BY status""", (organization_id,)
        ).fetchall()
    return {"items": _json([dict(x) for x in summary])}

@router.get("/{organization_id}/payments/attempts")
def list_payment_attempts(
    organization_id: int,
    request: Request,
    caller: Caller = Depends(member_caller),
):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        rows = cn.execute(
            """SELECT id,provider,idempotency_key,provider_reference,amount,currency,
            status,subscription_id,metadata,created_at,updated_at FROM payment_attempts
            WHERE organization_id=%s ORDER BY id DESC LIMIT 100""",
            (organization_id,),
        ).fetchall()
    return {"items": _json([dict(x) for x in rows])}


@public_router.get("/zarinpal/callback")
def zarinpal_callback(
    request: Request,
    organization_id: int,
    payment_attempt_id: int,
    Status: str | None = None,
    Authority: str | None = None,
):
    if not Authority:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "ZarinPal authority is missing")
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        attempt = cn.execute(
            """SELECT id,organization_id,amount,currency,status,provider_reference,subscription_id
               FROM payment_attempts
               WHERE id=%s AND organization_id=%s AND provider='zarinpal' FOR UPDATE""",
            (payment_attempt_id, organization_id),
        ).fetchone()
        if not attempt:
            raise ApiError(ErrorCode.NOT_FOUND, "payment attempt not found")
        if attempt["provider_reference"] and attempt["provider_reference"] != Authority:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "ZarinPal authority mismatch")
        if attempt["status"] == "succeeded":
            return {"status": "succeeded", "payment_attempt_id": payment_attempt_id, "already_verified": True}
        if Status != "OK":
            if attempt["status"] in {"created", "pending"}:
                cn.execute(
                    """UPDATE payment_attempts SET status='cancelled',updated_at=NOW()
                       WHERE id=%s AND organization_id=%s AND status IN ('created','pending')""",
                    (payment_attempt_id, organization_id),
                )
                return {"status": "cancelled", "payment_attempt_id": payment_attempt_id}
            return {"status": attempt["status"], "payment_attempt_id": payment_attempt_id}
        if attempt["status"] not in {"created", "pending", "succeeded"}:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "payment is no longer eligible for verification")
        amount = Decimal(str(attempt["amount"]))
        currency = str(attempt["currency"])
        provider = ZarinPalProvider(request.app.state.settings)

    verified = provider.verify(Authority, amount, currency)
    updated = _complete_verified_attempt(
        request,
        payment_attempt_id,
        organization_id,
        Authority,
        {"ref_id": verified.get("ref_id"), "verified_code": verified["code"]},
    )
    return {
        "status": "succeeded",
        "payment_attempt_id": payment_attempt_id,
        "authority": Authority,
        "ref_id": verified.get("ref_id"),
        "payment": _json(updated),
    }


@router.post("/{organization_id}/payments/webhook", status_code=202)
def payment_webhook(organization_id: int, payload: PaymentWebhookInput, request: Request):
    from .platform_settings_api import read_setting_value
    configured_secret = (read_setting_value("zarinpal_webhook_secret") or os.environ.get("PAYMENT_WEBHOOK_SECRET", "")).strip()
    supplied_secret = request.headers.get("X-Payment-Webhook-Secret", "")
    if not configured_secret or not hmac.compare_digest(supplied_secret, configured_secret):
        raise ApiError(ErrorCode.PERMISSION_DENIED, "invalid payment webhook signature")
    if payload.organization_id not in (None, organization_id):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "organization mismatch")
    provider_name = payload.provider.strip().lower()
    if provider_name != "zarinpal":
        raise ApiError(ErrorCode.VALIDATION_ERROR, "unsupported payment webhook provider")
    allowed = {"created", "pending", "succeeded", "failed", "cancelled"}
    if payload.status is not None and payload.status not in allowed:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "invalid payment status")
    # A shared application webhook secret authenticates the sender, but it is
    # not a gateway receipt. Successful payments must pass the provider's
    # amount-bound verification endpoint before they can activate a subscription.
    if payload.status == "succeeded":
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "successful payments must be verified through the payment provider",
        )
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(_db(request), row_factory=dict_row) as cn:
        event = cn.execute(
            """INSERT INTO subscription_events
            (organization_id,provider,event_id,event_type,payload,processed_at)
            VALUES(%s,%s,%s,%s,%s,NOW())
            ON CONFLICT(provider,event_id) DO NOTHING RETURNING id""",
            (
                organization_id,
                payload.provider,
                payload.event_id,
                payload.event_type,
                psycopg.types.json.Jsonb(payload.payload),
            ),
        ).fetchone()
        if not event:
            return {"accepted": True, "duplicate": True}
        if payload.payment_attempt_id is not None:
            attempt = cn.execute(
                "SELECT id,status,provider FROM payment_attempts WHERE id=%s AND organization_id=%s FOR UPDATE",
                (payload.payment_attempt_id, organization_id),
            ).fetchone()
            if not attempt:
                raise ApiError(ErrorCode.NOT_FOUND, "payment attempt not found")
            if attempt["provider"] != provider_name:
                raise ApiError(ErrorCode.VALIDATION_ERROR, "payment provider does not match the attempt")
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
                cn.execute(
                    """UPDATE payment_attempts SET status=%s,
                       provider_reference=COALESCE(%s,provider_reference),updated_at=NOW()
                       WHERE id=%s AND organization_id=%s AND provider=%s""",
                    (payload.status, payload.provider_reference, payload.payment_attempt_id,
                     organization_id, provider_name),
                )
    return {"accepted": True, "duplicate": False, "event_id": payload.event_id}
