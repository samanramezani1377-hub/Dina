from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import httpx

from .errors import ApiError, ErrorCode

PRODUCTION_API = "https://api.zarinpal.com/pg/v4"
PRODUCTION_STARTPAY = "https://www.zarinpal.com/pg/StartPay/"
SANDBOX_API = "https://sandbox.zarinpal.com/pg/v4"
SANDBOX_STARTPAY = "https://sandbox.zarinpal.com/pg/StartPay/"


class ZarinPalProvider:
    """ZarinPal REST v4 adapter.

    Dina stores the original amount/currency and only converts to Rial at the
    gateway boundary. This keeps accounting amounts independent from gateway
    quirks and makes verification use exactly the amount originally requested.
    """

    name = "zarinpal"

    def __init__(self, settings) -> None:
        self.merchant_id = settings.zarinpal_merchant_id.strip()
        self.callback_url = settings.zarinpal_callback_url.strip()
        self.sandbox = settings.zarinpal_sandbox
        self.timeout = settings.zarinpal_timeout_seconds
        if not self.merchant_id:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "ZarinPal merchant id is not configured")
        if not self.callback_url:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "ZarinPal callback URL is not configured")

    @property
    def api_base(self) -> str:
        return SANDBOX_API if self.sandbox else PRODUCTION_API

    @property
    def startpay_base(self) -> str:
        return SANDBOX_STARTPAY if self.sandbox else PRODUCTION_STARTPAY

    def _rial_amount(self, amount: Decimal, currency: str) -> int:
        normalized = currency.strip().upper()
        if normalized == "IRT" or normalized in {"TOMAN", "IRHT", "IRHR"}:
            value = amount * Decimal("10")
        elif normalized == "IRR":
            value = amount
        else:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "ZarinPal supports IRR or IRT amounts")
        rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if rounded <= 0:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "ZarinPal amount must be positive")
        return int(rounded)

    def _callback(self, organization_id: int, payment_attempt_id: int) -> str:
        parts = urlsplit(self.callback_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update({
            "organization_id": str(organization_id),
            "payment_attempt_id": str(payment_attempt_id),
        })
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def create_payment(
        self,
        amount: Decimal,
        currency: str,
        reference: str,
        organization_id: int,
        payment_attempt_id: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "merchant_id": self.merchant_id,
            "amount": self._rial_amount(amount, currency),
            "callback_url": self._callback(organization_id, payment_attempt_id),
            "description": str(metadata.get("description") or f"Dina payment {reference}")[:500],
            "metadata": {
                key: str(value)
                for key, value in metadata.items()
                if key in {"email", "mobile", "order_id"}
            },
        }
        try:
            response = httpx.post(
                f"{self.api_base}/payment/request.json",
                json=payload,
                headers={"User-Agent": "Dina/1 ZarinPal-REST-v4"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiError(ErrorCode.INTERNAL_ERROR, "ZarinPal request failed") from exc

        data = body.get("data") or {}
        code = data.get("code")
        if code != 100 or not data.get("authority"):
            errors = body.get("errors") or {}
            message = str(errors.get("message") or data.get("message") or "ZarinPal payment request failed")
            raise ApiError(ErrorCode.VALIDATION_ERROR, message[:300])
        authority = str(data["authority"])
        return {
            "authority": authority,
            "payment_url": f"{self.startpay_base}{authority}",
            "gateway_code": code,
            "gateway_response": data,
        }

    def verify(self, authority: str, amount: Decimal, currency: str) -> dict[str, Any]:
        payload = {
            "merchant_id": self.merchant_id,
            "authority": authority,
            "amount": self._rial_amount(amount, currency),
        }
        try:
            response = httpx.post(
                f"{self.api_base}/payment/verify.json",
                json=payload,
                headers={"User-Agent": "Dina/1 ZarinPal-REST-v4"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiError(ErrorCode.INTERNAL_ERROR, "ZarinPal verification failed") from exc

        data = body.get("data") or {}
        code = data.get("code")
        if code not in (100, 101):
            errors = body.get("errors") or {}
            message = str(errors.get("message") or data.get("message") or "ZarinPal verification failed")
            raise ApiError(ErrorCode.VALIDATION_ERROR, message[:300])
        return {
            "verified": True,
            "code": code,
            "ref_id": data.get("ref_id"),
            "card_pan": data.get("card_pan"),
            "card_hash": data.get("card_hash"),
            "gateway_response": data,
        }
