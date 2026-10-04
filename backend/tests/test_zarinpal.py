from decimal import Decimal

import httpx
import pytest

from src.config import Settings
from src.errors import ApiError
from src.zarinpal import ZarinPalProvider


def settings(**overrides):
    values = {
        "environment": "test",
        "zarinpal_merchant_id": "merchant-test",
        "zarinpal_callback_url": "https://api.example.test/api/v1/payments/zarinpal/callback",
        "zarinpal_sandbox": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_irt_amount_is_converted_to_rial():
    provider = ZarinPalProvider(settings())
    assert provider._rial_amount(Decimal("1250"), "IRT") == 12500
    assert provider._rial_amount(Decimal("1250"), "IRR") == 1250


def test_unsupported_currency_is_rejected():
    provider = ZarinPalProvider(settings())
    with pytest.raises(ApiError):
        provider._rial_amount(Decimal("10"), "EUR")


def test_request_uses_v4_payload_and_returns_startpay(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return httpx.Response(
            200,
            json={"data": {"code": 100, "authority": "A123"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("src.zarinpal.httpx.post", fake_post)
    result = ZarinPalProvider(settings()).create_payment(
        Decimal("1000"),
        "IRT",
        "42",
        7,
        42,
        {"description": "Dina test", "email": "test@example.com"},
    )
    assert captured["url"].endswith("/payment/request.json")
    assert captured["json"]["amount"] == 10000
    assert captured["json"]["merchant_id"] == "merchant-test"
    assert result["authority"] == "A123"
    assert result["payment_url"].endswith("/A123")


def test_verify_accepts_100_and_101(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(
            200,
            json={"data": {"code": 101, "ref_id": 987654}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("src.zarinpal.httpx.post", fake_post)
    result = ZarinPalProvider(settings()).verify("A123", Decimal("1000"), "IRT")
    assert result["verified"] is True
    assert result["code"] == 101
    assert calls[0]["amount"] == 10000
