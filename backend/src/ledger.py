"""Ledger computation over posted journal entries.

Everything here is exact ``Decimal`` arithmetic. There is no float anywhere in
the module, including in the sign handling, because a balance that is off in the
tenths of a unit is a wrong balance.

Three ideas carry the module:

**Only posted facts count.** The store hands over ``posted`` and ``reversed``
entries (:data:`src.models.LEDGER_STATUSES`); a draft never reaches here. A
reversed entry is still a fact that happened, and it is included next to the
entry that reverses it, so the pair nets to zero instead of the original
vanishing.

**The sign follows the account type.** An asset grows on the debit side and a
liability grows on the credit side. A balance is therefore
``debit - credit`` for a debit-normal account and ``credit - debit`` for a
credit-normal one, so a liability the business owes reads as a positive number
rather than a permanently negative one. Deciding this once, from the account
type, is what stops each report from re-deriving it differently.

**The order is total and stated.** Lines are stepped in ``(entry id, line no)``
order. Ids are unique and a line number is unique inside its entry, so no two
lines can tie and the running balance is reproducible: the same ledger always
renders the same sequence for the same data, which is what makes a running
balance worth printing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .accounting_store import AccountingStore
from .models import Account, EntryLine, JournalEntry
from .money import format_money, money

#: The sign that converts a raw (debit - credit) movement into a balance in the
#: account's own normal direction. See the module docstring.
_DEBIT_NORMAL_SIGN = 1
_CREDIT_NORMAL_SIGN = -1


def _sign(account: Account) -> int:
    return _DEBIT_NORMAL_SIGN if account.normal_balance == "debit" else _CREDIT_NORMAL_SIGN


@dataclass(frozen=True)
class LedgerFilter:
    """The query parameters the ledger endpoint accepts.

    ``date_from`` and ``date_to`` are inclusive on ``entry_date`` and bound the
    *period*: the opening balance is everything strictly before ``date_from``.
    ``entry_id`` and ``document_no`` are alternative ways to name a single entry;
    supplying both is allowed and then both must match.
    """

    account_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    entry_id: int | None = None
    document_no: str | None = None

    def includes_entry(self, entry: JournalEntry) -> bool:
        if self.entry_id is not None and entry.id != self.entry_id:
            return False
        if self.document_no is not None and entry.document_no != self.document_no:
            return False
        return True

    def in_period(self, entry: JournalEntry) -> bool:
        if self.date_from is not None and entry.entry_date < self.date_from:
            return False
        if self.date_to is not None and entry.entry_date > self.date_to:
            return False
        return True


@dataclass(frozen=True)
class LedgerMovement:
    """One line of the running balance, with the balance it produced."""

    entry_id: int
    line_no: int
    account_id: int
    document_no: str
    description: str
    entry_date: date
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


@dataclass(frozen=True)
class AccountLedger:
    """One account's ledger for the requested period.

    ``opening_balance`` is the signed balance carried in from before
    ``date_from``; ``closing_balance`` is what is carried out. With no
    ``date_from`` the period has no history before it and the opening balance is
    zero, which is why an unfiltered report of a new organization is empty
    rather than showing every historical figure twice.
    """

    account: Account
    opening_balance: Decimal
    period_debit_total: Decimal
    period_credit_total: Decimal
    closing_balance: Decimal
    movements: tuple[LedgerMovement, ...]

    @property
    def is_empty(self) -> bool:
        return not self.movements and self.opening_balance == 0


@dataclass(frozen=True)
class Ledger:
    """The whole ledger for one organization, plus the per-period totals."""

    organization_id: int
    accounts: tuple[AccountLedger, ...]
    period_debit_total: Decimal
    period_credit_total: Decimal
    net_movement: Decimal

    @property
    def is_balanced(self) -> bool:
        """Whether the period's debits equal its credits.

        Reported rather than assumed. A false here is a data problem the
        operator has to see; the ledger does not quietly correct it.
        """
        return self.period_debit_total == self.period_credit_total


def _movement_amount(line: EntryLine, sign: int) -> Decimal:
    """Signed effect of one line on its account's normal balance."""
    return sign * (line.debit - line.credit)


def _ordered_lines(entries: list[JournalEntry]) -> list[tuple[JournalEntry, EntryLine]]:
    """Every line of ``entries`` in ``(entry id, line no)`` order."""
    pairs = [(entry, line) for entry in entries for line in entry.lines]
    pairs.sort(key=lambda pair: (pair[0].id, pair[1].line_no))
    return pairs


def _account_ledger(
    account: Account, entries: list[JournalEntry], ledger_filter: LedgerFilter
) -> AccountLedger:
    """Build one account's ledger, stepping its lines in canonical order."""
    sign = _sign(account)
    lines = [
        (entry, line)
        for entry, line in _ordered_lines(entries)
        if line.account_id == account.id
    ]

    opening = money(0)
    period_debit = money(0)
    period_credit = money(0)
    movements: list[LedgerMovement] = []
    # The running balance starts from whatever the account carried into the
    # period, so the first period movement is seeded with it rather than zero.
    running = opening

    for entry, line in lines:
        if ledger_filter.in_period(entry):
            running = running + _movement_amount(line, sign)
            period_debit = period_debit + line.debit
            period_credit = period_credit + line.credit
            movements.append(
                LedgerMovement(
                    entry_id=entry.id,
                    line_no=line.line_no,
                    account_id=line.account_id,
                    document_no=entry.document_no,
                    description=entry.description,
                    entry_date=entry.entry_date,
                    debit=line.debit,
                    credit=line.credit,
                    running_balance=running,
                )
            )
        elif ledger_filter.date_from is not None and entry.entry_date < ledger_filter.date_from:
            # Strictly before the period opens: history that becomes the
            # opening balance, not movement within the period. Lines dated
            # after `date_to` land in neither branch and are ignored, which is
            # what a period report is supposed to do with the future.
            opening = opening + _movement_amount(line, sign)
            running = opening

    return AccountLedger(
        account=account,
        opening_balance=opening,
        period_debit_total=period_debit,
        period_credit_total=period_credit,
        closing_balance=running,
        movements=tuple(movements),
    )


def build_ledger(
    store: AccountingStore,
    organization_id: int,
    ledger_filter: LedgerFilter | None = None,
) -> Ledger:
    """Compute the ledger of ``organization_id``.

    Only the requested organization's rows are read; a filter naming an account
    or entry from another organization raises before any arithmetic happens, so
    a cross-tenant id can never contribute a cent to a balance.

    An organization with nothing posted produces a :class:`Ledger` with no
    accounts and zero totals. That is a well-formed empty report, not an error:
    "no transactions yet" is a normal state for a new business, and failing the
    request would make the client guess.

    Raises:
        src.accounting_store.AccountingError: ``organization_not_found``,
            ``account_not_found`` or ``journal_not_found`` when a filter names
            a row this organization does not own.
    """
    ledger_filter = ledger_filter or LedgerFilter()
    if ledger_filter.account_id is not None:
        # Resolving the account is what enforces tenancy: an id belonging to
        # another organization raises instead of yielding an empty report that
        # reads like "this account has no activity".
        store.get_account(organization_id, ledger_filter.account_id)
    if ledger_filter.entry_id is not None:
        store.get_entry(organization_id, ledger_filter.entry_id)

    entries = [
        entry
        for entry in store.ledger_entries(organization_id)
        if ledger_filter.includes_entry(entry)
    ]

    if ledger_filter.account_id is not None:
        accounts = [store.get_account(organization_id, ledger_filter.account_id)]
    else:
        accounts = [
            account
            for account in store.list_accounts(organization_id)
            if any(line.account_id == account.id for entry in entries for line in entry.lines)
        ]

    account_ledgers = tuple(
        _account_ledger(account, entries, ledger_filter) for account in accounts
    )
    period_debit = money(0)
    period_credit = money(0)
    for account_ledger in account_ledgers:
        period_debit = period_debit + account_ledger.period_debit_total
        period_credit = period_credit + account_ledger.period_credit_total
    return Ledger(
        organization_id=organization_id,
        accounts=account_ledgers,
        period_debit_total=period_debit,
        period_credit_total=period_credit,
        net_movement=period_debit - period_credit,
    )


def ledger_to_dict(ledger: Ledger) -> dict[str, object]:
    """Render a :class:`Ledger` as exact decimal strings for the API.

    Money is stringified rather than serialised as a number: a JSON number with
    a fractional part comes back out of most JSON parsers as a binary float, and
    ``"1250.75"`` would not survive the round trip. The string is what a client
    must display or re-parse, and the format is fixed by
    :func:`src.money.format_money`.
    """
    return {
        "organization_id": ledger.organization_id,
        "period_debit_total": format_money(ledger.period_debit_total),
        "period_credit_total": format_money(ledger.period_credit_total),
        "net_movement": format_money(ledger.net_movement),
        "is_balanced": ledger.is_balanced,
        "accounts": [
            {
                "account_id": account_ledger.account.id,
                "account_code": account_ledger.account.code,
                "account_name": account_ledger.account.name,
                "account_type": account_ledger.account.account_type,
                "normal_balance": account_ledger.account.normal_balance,
                "opening_balance": format_money(account_ledger.opening_balance),
                "period_debit_total": format_money(account_ledger.period_debit_total),
                "period_credit_total": format_money(account_ledger.period_credit_total),
                "closing_balance": format_money(account_ledger.closing_balance),
                "movements": [
                    {
                        "entry_id": movement.entry_id,
                        "line_no": movement.line_no,
                        "document_no": movement.document_no,
                        "description": movement.description,
                        "entry_date": movement.entry_date.isoformat(),
                        "debit": format_money(movement.debit),
                        "credit": format_money(movement.credit),
                        "running_balance": format_money(movement.running_balance),
                    }
                    for movement in account_ledger.movements
                ],
            }
            for account_ledger in ledger.accounts
        ],
    }
