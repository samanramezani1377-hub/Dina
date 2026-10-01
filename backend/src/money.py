"""Exact money handling for the ledger.

Every amount in Dina is a ``Decimal``. The rules enforced here are deliberately
strict because a silent coercion is how an accounting system starts losing
cents:

* A ``float`` is refused outright. ``Decimal(0.1)`` is not ``0.1``; it is
  ``0.1000000000000000055511151231257827...``. Accepting one at any point in
  the pipeline means every balance derived from it is quietly wrong.
* Arithmetic is exact. Sums of decimals do not accumulate error the way
  binary floating point does, so nothing here rounds intermediate values.
* Values are quantized to :data:`MONEY_SCALE`, matching the ``NUMERIC(20,4)``
  columns in ``database/migrations/001_accounting_core.sql``, and rendered as
  strings so a JSON client receives ``"1250.75"`` and not ``1250.75`` (which a
  JSON parser would hand back as a binary float).

Quantizing to the storage scale rather than leaving an arbitrary exponent is
also what keeps the output deterministic: the same sum always renders as the
same string, so a running balance can be compared exactly in a test and in a
diff between two reports.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

#: Storage scale for money: four decimal places, per the ``NUMERIC(20,4)``
#: columns the migration creates.
MONEY_SCALE = Decimal("0.0001")

#: Smallest number of decimal places a rendered amount carries. Amounts with
#: more significant decimals keep all four; amounts with fewer are padded so
#: ``100`` renders as ``"100.00"`` rather than ``"100"``.
MIN_DISPLAY_PLACES = 2


class MoneyError(ValueError):
    """Raised when a value cannot be treated as an exact monetary amount."""


def to_money(value: object) -> Decimal:
    """Return ``value`` as an exact, scale-quantized :class:`Decimal`.

    Accepts ``Decimal``, ``int`` and ``str``. Strings are parsed rather than
    accepted verbatim so ``"12.5"`` and ``"12.50"`` become the same amount and
    cannot produce two different renderings of one figure.

    Raises:
        MoneyError: if ``value`` is a ``float``, is not a finite decimal, or
            carries more precision than :data:`MONEY_SCALE` stores. Precision is
            refused instead of rounded because a caller who passed
            ``"0.00005"`` has a bug that silent truncation would hide.
    """
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, bool):
        # bool is an int subclass, and True silently becoming Decimal("1") is
        # exactly the kind of coercion this module exists to prevent.
        raise MoneyError("a boolean is not a monetary amount")
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, str):
        try:
            amount = Decimal(value.strip())
        except InvalidOperation as exc:
            raise MoneyError(f"{value!r} is not a decimal amount") from exc
    elif isinstance(value, float):
        raise MoneyError(
            "floating point amounts are refused; pass a Decimal or a string "
            "such as \"1250.75\""
        )
    else:
        raise MoneyError(f"{type(value).__name__} is not a monetary amount")

    if not amount.is_finite():
        raise MoneyError(f"{amount} is not a finite amount")

    if amount.as_tuple().exponent < MONEY_SCALE.as_tuple().exponent:
        raise MoneyError(
            f"{amount} has more decimal places than the {MONEY_SCALE}-scaled "
            "money column stores"
        )
    return amount.quantize(MONEY_SCALE)


def money(value: object) -> Decimal:
    """Sum-initialised alias of :func:`to_money` for use with ``sum(...)``."""
    return to_money(value)


def format_money(value: Decimal) -> str:
    """Render ``value`` as an exact decimal string for the API.

    The result never uses scientific notation, never carries a negative zero and
    always has at least :data:`MIN_DISPLAY_PLACES` decimal places, so a test can
    assert equality on the string itself.
    """
    amount = to_money(value)
    if amount == 0:
        # Collapses -0.0000, which is arithmetically zero but would otherwise
        # render as "-0.0000" and read like a real negative balance.
        amount = amount.copy_abs()
    text = f"{amount:f}"
    whole, _, fraction = text.partition(".")
    fraction = fraction.rstrip("0")
    if len(fraction) < MIN_DISPLAY_PLACES:
        fraction = fraction.ljust(MIN_DISPLAY_PLACES, "0")
    return f"{whole}.{fraction}"