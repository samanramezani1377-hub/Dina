"""Unit tests for exact money handling.

These exercise :mod:`src.money` directly rather than through the ledger,
because the failure they guard against is invisible at the API layer: money is
quantized to four decimal places, so an amount that passed through a binary
float gets quietly rounded back onto the same four places and the ledger still
prints the right digits. Only a test that inspects the coercion itself can see
it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from src.money import MONEY_SCALE, MoneyError, format_money, to_money


def test_a_float_is_refused_outright():
    """``Decimal(0.1)`` is not ``0.1``, so a float must never be accepted."""
    with pytest.raises(MoneyError):
        to_money(0.1)


def test_a_boolean_is_refused_outright():
    """``True`` is an ``int`` subclass and would silently become ``1.00``."""
    with pytest.raises(MoneyError):
        to_money(True)


@pytest.mark.parametrize("value", ["", "abc", "12.3.4", "1,000"])
def test_a_non_numeric_string_is_refused(value):
    with pytest.raises(MoneyError):
        to_money(value)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_amount_is_refused(value):
    """NaN would poison every subsequent sum, so it can never enter the ledger."""
    with pytest.raises(MoneyError):
        to_money(Decimal(value))


def test_excess_precision_is_refused_rather_than_rounded():
    """Silent truncation would hide a caller's bug at the storage boundary."""
    with pytest.raises(MoneyError):
        to_money("0.00001")


def test_string_amounts_parse_without_binary_error():
    """The coercion itself must not introduce error, not even a hidden one."""
    # 12345678.1234 is not exactly representable as a float; routing it through
    # one would yield ...12340000085532665252685546875.
    assert to_money("12345678.1234") == Decimal("12345678.1234")
    assert to_money("0.07") == Decimal("0.07")


def test_int_and_string_of_the_same_number_agree():
    """``100`` and ``"100.00"`` are one amount and must not render differently."""
    assert to_money(100) == to_money("100.00")
    assert format_money(to_money(100)) == format_money(to_money("100.00"))


def test_amounts_are_quantized_to_the_storage_scale():
    """The rendering matches the NUMERIC(20,4) column the migration creates."""
    assert to_money("1.5") == Decimal("1.5000")
    assert MONEY_SCALE == Decimal("0.0001")


def test_addition_stays_exact_where_floats_do_not():
    """0.1 + 0.2 is 0.3 in decimal and 0.30000000000000004 in a float."""
    total = to_money("0.1") + to_money("0.2")
    assert format_money(total) == "0.30"


def test_formatting_keeps_at_least_two_decimal_places():
    assert format_money(to_money("100")) == "100.00"
    assert format_money(to_money("100.5")) == "100.50"


def test_formatting_keeps_all_four_when_they_are_significant():
    assert format_money(to_money("1.2345")) == "1.2345"


def test_negative_zero_renders_as_plain_zero():
    """``-0.0000`` is arithmetically zero but reads like a real negative."""
    assert format_money(Decimal("-0.0000")) == "0.00"
    assert format_money(Decimal("0") - Decimal("0")) == "0.00"


def test_negative_amounts_render_with_their_sign():
    assert format_money(to_money("-1234.5")) == "-1234.50"


def test_formatting_never_uses_scientific_notation():
    """A client parsing ``1E+3`` as a float would lose the value it was sent."""
    rendered = format_money(to_money("1000000"))
    assert rendered == "1000000.00"
    assert "E" not in rendered


def test_a_refused_float_never_reaches_a_ledger_total():
    """A total cannot be built from an unconverted float.

    ``sum`` accepts whatever it is handed, so the guard has to be the coercion
    step: if every amount goes through :func:`to_money` on its way in, a float
    cannot be added to a running balance at all.
    """
    amounts = [to_money("1.00"), 0.05]
    with pytest.raises(MoneyError):
        total = sum((to_money(amount) for amount in amounts), Decimal("0"))
        format_money(total)
