from decimal import Decimal


def test_double_entry_balances():
    lines = [
        (Decimal("100.00"), Decimal("0")),
        (Decimal("0"), Decimal("100.00")),
    ]
    assert sum(d for d, _ in lines) == sum(c for _, c in lines)
