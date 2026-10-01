"""In-process store for the chart of accounts and journal entries.

The ledger has to be computed from posted entries that belong to the caller's
own organization, so this module is where that ownership is established: an
account or entry is created inside exactly one organization, and every read
takes an ``organization_id`` and refuses to hand back a row from anywhere else.
Tenant isolation here is a property of the read path, not a filter a caller can
forget to apply, because a filter that is easy to omit is a data leak waiting to
happen.

This is deliberately an in-process store rather than direct SQL: the schema and
migration in ``database/migrations`` are the contract, and the ledger must be
computable and testable without a live server. When the PostgreSQL repository
lands it implements the same methods against the same tables, and
:mod:`src.ledger` does not change.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from itertools import count

from .accounting import validate_journal
from .errors import ApiError, ErrorCode
from .models import (
    ACCOUNT_TYPES,
    DRAFT,
    LEDGER_STATUSES,
    POSTED,
    REVERSED,
    Account,
    EntryLine,
    JournalEntry,
    JournalLine,
)
from .money import to_money


class AccountingError(ApiError, ValueError):
    """A domain rule refused an operation, carrying its public error code.

    Also a :class:`ValueError`, because that is what it always was and callers
    that catch the base class must keep working. The code is what a client sees;
    the message is for the log.
    """


class AccountingStore:
    """Accounts and journal entries for every organization in the process."""

    def __init__(self) -> None:
        self._organizations: set[int] = set()
        self._accounts: dict[int, Account] = {}
        self._entries: dict[int, JournalEntry] = {}
        self._account_ids = count(1)
        self._entry_ids = count(1)

    # -- organizations ----------------------------------------------------

    def add_organization(self, organization_id: int) -> None:
        self._organizations.add(organization_id)

    def organization_exists(self, organization_id: int) -> bool:
        return organization_id in self._organizations

    # -- accounts ---------------------------------------------------------

    def add_account(
        self,
        organization_id: int,
        code: str,
        name: str,
        account_type: str,
    ) -> Account:
        """Create an account owned by ``organization_id``.

        Raises:
            AccountingError: ``organization_not_found`` if the organization is
                unknown, ``invalid_account_type`` for a type outside
                :data:`src.models.ACCOUNT_TYPES`, or ``account_code_conflict``
                when the code is already used in that organization. The
                uniqueness check is per organization, so two organizations can
                both have account ``1100``.
        """
        self._require_organization(organization_id)
        normalised_type = account_type.strip().lower()
        if normalised_type not in ACCOUNT_TYPES:
            raise AccountingError(
                ErrorCode.INVALID_ACCOUNT_TYPE,
                f"account_type must be one of {', '.join(ACCOUNT_TYPES)}",
            )
        for account in self._accounts.values():
            if account.organization_id == organization_id and account.code == code:
                raise AccountingError(
                    ErrorCode.ACCOUNT_CODE_CONFLICT,
                    f"account code {code} already exists in this organization",
                )
        account = Account(
            id=next(self._account_ids),
            organization_id=organization_id,
            code=code,
            name=name,
            account_type=normalised_type,
        )
        self._accounts[account.id] = account
        return account

    def get_account(self, organization_id: int, account_id: int) -> Account:
        """Return the account, or raise if it is absent or another tenant's.

        A cross-tenant id is reported as ``account_not_found`` rather than
        ``permission_denied``: the caller learns nothing about which ids exist
        outside their organization, so an id-guessing scan cannot map the
        database. It is also never silently summed into a report.
        """
        account = self._accounts.get(account_id)
        if account is None or account.organization_id != organization_id:
            raise AccountingError(
                ErrorCode.ACCOUNT_NOT_FOUND,
                f"account {account_id} does not exist in this organization",
            )
        return account

    def list_accounts(self, organization_id: int) -> list[Account]:
        return sorted(
            (
                account
                for account in self._accounts.values()
                if account.organization_id == organization_id
            ),
            key=lambda account: (account.code, account.id),
        )

    # -- entries ----------------------------------------------------------

    def add_entry(
        self,
        organization_id: int,
        document_no: str,
        description: str,
        entry_date: date,
        lines: list[JournalLine],
        status: str = DRAFT,
        reversal_of_entry_id: int | None = None,
    ) -> JournalEntry:
        """Validate ``lines`` and store an entry with them.

        Every account referenced by a line must belong to ``organization_id``.
        That check runs before anything is written, so a journal that names
        another tenant's account is rejected with nothing persisted.

        Raises:
            AccountingError: any code raised by :func:`src.accounting.validate_journal`,
                plus ``account_not_found`` for a cross-tenant account,
                ``document_no_conflict`` for a reused document number and
                ``invalid_entry_status`` for an unknown status.
        """
        self._require_organization(organization_id)
        if status not in {DRAFT, POSTED, REVERSED}:
            raise AccountingError(
                ErrorCode.INVALID_ENTRY_STATUS,
                f"unknown entry status {status!r}",
            )
        if not lines:
            raise AccountingError(
                ErrorCode.JOURNAL_EMPTY, "a journal entry must have at least one line"
            )
        for line in lines:
            self.get_account(organization_id, line.account_id)
        for entry in self._entries.values():
            if (
                entry.organization_id == organization_id
                and entry.document_no == document_no
            ):
                raise AccountingError(
                    ErrorCode.DOCUMENT_NO_CONFLICT,
                    f"document number {document_no} already exists in this organization",
                )
        try:
            validate_journal(lines)
        except ApiError as exc:
            # The journal rules already speak the error contract; re-wrapping
            # keeps the same code and details under the store's own exception so
            # a caller can still catch AccountingError alone.
            raise AccountingError(exc.code, exc.message, exc.details) from exc

        entry_id = next(self._entry_ids)
        stored = JournalEntry(
            id=entry_id,
            organization_id=organization_id,
            document_no=document_no,
            description=description,
            status=status,
            entry_date=entry_date,
            posted_at=datetime.now(timezone.utc) if status != DRAFT else None,
            reversal_of_entry_id=reversal_of_entry_id,
            lines=tuple(
                EntryLine(
                    entry_id=entry_id,
                    line_no=position,
                    account_id=line.account_id,
                    debit=to_money(line.debit),
                    credit=to_money(line.credit),
                )
                for position, line in enumerate(lines, start=1)
            ),
        )
        self._entries[entry_id] = stored
        return stored

    def get_entry(self, organization_id: int, entry_id: int) -> JournalEntry:
        """Return the entry, or raise if absent or owned by another tenant."""
        entry = self._entries.get(entry_id)
        if entry is None or entry.organization_id != organization_id:
            raise AccountingError(
                ErrorCode.JOURNAL_NOT_FOUND,
                f"journal entry {entry_id} does not exist in this organization",
            )
        return entry

    def post_entry(self, organization_id: int, entry_id: int) -> JournalEntry:
        """Move a draft to ``posted``.

        A posted entry is immutable from here on, and only its reversal may
        change what the ledger shows. Raises ``journal_immutable`` if the entry
        is already posted or reversed.
        """
        entry = self.get_entry(organization_id, entry_id)
        if entry.status != DRAFT:
            raise AccountingError(
                ErrorCode.JOURNAL_IMMUTABLE,
                f"entry {entry_id} is {entry.status} and cannot be posted again",
            )
        return self._store(replace(entry, status=POSTED, posted_at=datetime.now(timezone.utc)))

    def reverse_entry(
        self,
        organization_id: int,
        entry_id: int,
        document_no: str,
        entry_date: date,
        description: str = "",
    ) -> JournalEntry:
        """Reverse a posted entry by writing its mirror image.

        The original keeps its lines and is marked ``reversed``; a new posted
        entry with every debit swapped for a credit is appended and points back
        at it. Both stay in the ledger (see
        :data:`src.models.LEDGER_STATUSES`), so the pair nets to zero and a
        reader can still see what happened.

        The mirror is written *before* the original's status flips, so a call
        rejected by :meth:`add_entry` leaves the original posted and still
        reversible. Flipping first would mark an entry ``reversed`` with no
        reversing entry behind it, and the retry would then fail as
        ``journal_not_reversible`` — a state the caller cannot get out of.

        Raises:
            AccountingError: ``journal_not_reversible`` when the entry is not
                posted, ``entry_already_reversed`` when one exists already, or
                any code from :meth:`add_entry`.
        """
        original = self.get_entry(organization_id, entry_id)
        for entry in self._entries.values():
            if (
                entry.organization_id == organization_id
                and entry.reversal_of_entry_id == original.id
            ):
                # Checked before the status test below so a second reversal is
                # reported as what it is, rather than as the generic "not
                # reversible" that a `reversed` status would otherwise produce.
                # The caller needs to know a reversal already exists, because
                # that is a different mistake from reversing a draft.
                raise AccountingError(
                    ErrorCode.ENTRY_ALREADY_REVERSED,
                    f"entry {entry_id} has already been reversed by entry "
                    f"{entry.id}",
                )
        if original.status != POSTED:
            raise AccountingError(
                ErrorCode.JOURNAL_NOT_REVERSIBLE,
                f"only a posted entry can be reversed; entry {entry_id} is "
                f"{original.status}",
            )
        reversing = self.add_entry(
            organization_id=organization_id,
            document_no=document_no,
            description=description or f"reversal of {original.document_no}",
            entry_date=entry_date,
            lines=[
                JournalLine(
                    account_id=line.account_id,
                    debit=line.credit,
                    credit=line.debit,
                )
                for line in original.lines
            ],
            status=POSTED,
            reversal_of_entry_id=original.id,
        )
        # Only now that the mirror exists does the original become `reversed`,
        # so the two facts cannot disagree.
        self._store(replace(original, status=REVERSED))
        return reversing

    # -- ledger reads -----------------------------------------------------

    def ledger_entries(self, organization_id: int) -> list[JournalEntry]:
        """Posted and reversed entries of one organization, id order.

        Drafts are excluded. Reversed entries are included: a reversal is only
        legible when the entry it reverses is still visible.
        """
        self._require_organization(organization_id)
        return sorted(
            (
                entry
                for entry in self._entries.values()
                if entry.organization_id == organization_id
                and entry.status in LEDGER_STATUSES
            ),
            key=lambda entry: entry.id,
        )

    # -- internals --------------------------------------------------------

    def _require_organization(self, organization_id: int) -> None:
        if organization_id not in self._organizations:
            raise AccountingError(
                ErrorCode.ORGANIZATION_NOT_FOUND,
                f"organization {organization_id} does not exist",
            )

    def _store(self, entry: JournalEntry) -> JournalEntry:
        self._entries[entry.id] = entry
        return entry
