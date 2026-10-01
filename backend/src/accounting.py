"""The journal rules, and the codes the API answers them with.

Every refusal raised here is an :class:`~src.errors.ApiError` carrying a code
from :class:`~src.errors.ErrorCode` and facts in ``details`` — which line
failed, what the totals were, by how much the journal missed. A client can act
on the totals; the message is only there to be read.

The checks run in a fixed order, and the order is part of the contract: a
journal with no lines is ``journal_empty`` rather than a balance question, and a
negative amount is reported as such before the "exactly one side" rule can
complain about a line that is only wrong because of its sign. A caller fixing
one problem at a time must never be sent back to re-solve a problem it has
already solved.
"""

from decimal import Decimal

from .errors import ApiError, ErrorCode
from .models import JournalLine


def validate_journal(lines: list[JournalLine]) -> None:
    """Raise the first :class:`~src.errors.ApiError` the journal violates.

    Raises:
        ApiError: ``journal_empty``, ``amount_must_be_non_negative``,
            ``line_must_have_exactly_one_side`` or ``journal_not_balanced``.
    """
    if not lines:
        raise ApiError(
            ErrorCode.JOURNAL_EMPTY,
            "a journal entry must have at least one line",
            {"line_count": 0},
        )
    for position, line in enumerate(lines, start=1):
        if line.debit < 0 or line.credit < 0:
            raise ApiError(
                ErrorCode.AMOUNT_MUST_BE_NON_NEGATIVE,
                "debit and credit amounts must not be negative",
                {
                    "line_no": position,
                    "debit": str(line.debit),
                    "credit": str(line.credit),
                },
            )
        if (line.debit > 0) == (line.credit > 0):
            raise ApiError(
                ErrorCode.LINE_MUST_HAVE_EXACTLY_ONE_SIDE,
                "a journal line must carry either a debit or a credit, never both "
                "and never neither",
                {
                    "line_no": position,
                    "account_id": line.account_id,
                    "debit": str(line.debit),
                    "credit": str(line.credit),
                },
            )
    debit_total = sum((line.debit for line in lines), Decimal("0"))
    credit_total = sum((line.credit for line in lines), Decimal("0"))
    if debit_total != credit_total:
        raise ApiError(
            ErrorCode.JOURNAL_NOT_BALANCED,
            "total debits must equal total credits",
            {
                "debit_total": str(debit_total),
                "credit_total": str(credit_total),
                "difference": str(debit_total - credit_total),
            },
        )