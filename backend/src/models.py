from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

#: Account types the chart of accounts accepts. Kept identical to the CHECK
#: constraint in ``database/migrations/001_accounting_core.sql`` so the
#: in-process store and PostgreSQL cannot disagree about what is legal.
ACCOUNT_TYPES: tuple[str, ...] = (
    "asset",
    "liability",
    "equity",
    "revenue",
    "expense",
)

#: Account types whose balance grows on the debit side. Everything else
#: (liability, equity, revenue) is credit-normal. The ledger reports balances in
#: the account's own normal direction so a credit-normal account shows a
#: positive balance when it is owed something, which is what a reader of a
#: ledger expects. Deriving the sign from the account type, rather than
#: hard-coding "debit minus credit" everywhere, is what keeps revenue and
#: liability reports from reading as permanently negative.
DEBIT_NORMAL: frozenset[str] = frozenset({"asset", "expense"})
CREDIT_NORMAL: frozenset[str] = frozenset({"liability", "equity", "revenue"})


@dataclass(frozen=True)
class Organization:
    id: int
    name: str


@dataclass(frozen=True)
class Membership:
    user_id: int
    organization_id: int
    role: str


@dataclass(frozen=True)
class JournalLine:
    """A single validation-level line, before it is attached to an entry."""

    account_id: int
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class Account:
    """A chart-of-accounts account, always owned by exactly one organization."""

    id: int
    organization_id: int
    code: str
    name: str
    account_type: str

    @property
    def normal_balance(self) -> str:
        return "debit" if self.account_type in DEBIT_NORMAL else "credit"


@dataclass(frozen=True)
class EntryLine:
    """A persisted journal line.

    ``line_no`` is the position of the line inside its entry and is assigned by
    the store, never by the client. Together with ``entry_id`` it gives the
    ledger a total, reproducible ordering: no two lines of an entry can share a
    line number, and no two entries can share an id.
    """

    entry_id: int
    line_no: int
    account_id: int
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class JournalEntry:
    """A journal entry header plus its lines.

    ``status`` is one of :data:`ENTRY_STATUSES`. ``reversal_of_entry_id`` is
    set only on the entry produced by reversing another one; the mirrored
    original keeps its lines untouched, which is what makes an audit trail
    possible instead of a silent rewrite.
    """

    id: int
    organization_id: int
    document_no: str
    description: str
    status: str
    entry_date: date
    posted_at: datetime | None
    reversal_of_entry_id: int | None
    lines: tuple[EntryLine, ...] = field(default_factory=tuple)


#: The three entry states the schema allows.
DRAFT = "draft"
POSTED = "posted"
REVERSED = "reversed"
ENTRY_STATUSES: frozenset[str] = frozenset({DRAFT, POSTED, REVERSED})

#: Statuses that contribute to the ledger.
#:
#: ``reversed`` is in this set on purpose. A reversal is two facts, not one:
#: the original entry happened and was later undone. Dropping the original the
#: moment it is marked ``reversed`` would delete that fact and make the reversal
#: look like the only event, so the pair stays visible together and nets to
#: zero. Only ``draft`` is excluded, because a draft was never a financial fact.
LEDGER_STATUSES: frozenset[str] = frozenset({POSTED, REVERSED})
