from decimal import Decimal
from .models import JournalLine

def validate_journal(lines: list[JournalLine]) -> None:
    if not lines: raise ValueError("journal_must_have_lines")
    for line in lines:
        if line.debit < 0 or line.credit < 0: raise ValueError("amount_must_be_non_negative")
        if (line.debit > 0) == (line.credit > 0): raise ValueError("line_must_have_exactly_one_side")
    if sum((x.debit for x in lines), Decimal("0")) != sum((x.credit for x in lines), Decimal("0")): raise ValueError("journal_not_balanced")
