"""Trial balance: every account's cumulative debits and credits as of a date.

The report is a projection of :mod:`src.ledger`, not a second implementation of
it. A trial balance is the ledger read with a single bound — everything posted
up to ``as_of``, no lower bound — so it is built by handing :func:`src.ledger.
build_ledger` a :class:`src.ledger.LedgerFilter` whose only date is
``date_to=as_of``. Everything that makes the ledger correct therefore carries
over by construction rather than by being re-implemented and re-tested:

* only ``posted`` and ``reversed`` entries are read, so a draft never appears
  (:data:`src.models.LEDGER_STATUSES`);
* a reversal and the entry it reverses are both included and net to zero, so
  undoing a journal does not delete it from the report;
* the sign of a balance follows the account's normal direction, decided once in
  :mod:`src.ledger`, so a liability reads positive rather than negative;
* only the requested organization's rows are read, so a cross-tenant id cannot
  contribute a cent.

**An imbalance is reported, never repaired.** If the debits and credits of the
posted entries do not agree, the difference is computed, published in the
response, given a stable error code and written to the log and the audit trail.
The tempting alternative — nudging one side so the columns look equal — would
destroy the only evidence that the data is wrong, and would do it invisibly.
The figures returned are exactly the figures that were stored.

Amounts are exact ``Decimal`` values throughout and are rendered with
:func:`src.money.format_money`, so the API hands out decimal *strings*. A JSON
number would come back out of most parsers as a binary float, and ``"0.30"``
would not survive the round trip.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .accounting_store import AccountingStore
from .ledger import AccountLedger, LedgerFilter, build_ledger
from .money import format_money, money

logger = logging.getLogger("dina.trial_balance")

#: Stable, public error code for "the posted entries do not balance". Part of
#: the API contract: its meaning must not change, because a client switches on
#: it to decide that the books need a human.
TRIAL_BALANCE_UNBALANCED = "trial_balance_unbalanced"

#: Audit action recorded alongside every reported imbalance.
AUDIT_ACTION_TRIAL_BALANCE_UNBALANCED = "trial_balance.unbalanced_reported"

#: A recorder is :func:`src.audit.record`: keyword-only, and never allowed to
#: raise into the caller.
AuditRecorder = Callable[..., None]


@dataclass(frozen=True)
class TrialBalanceAccount:
    """One account's row of the trial balance.

    ``debit_total`` and ``credit_total`` are the raw, unsigned columns: what
    was posted to the debit side and to the credit side. ``balance`` is the net
    figure in the account's own normal direction, so it is the number a ledger
    screen shows; it is negative exactly when the account carries more on the
    side opposite to its type. Keeping the two raw columns alongside the signed
    balance is what lets a reader check the arithmetic instead of trusting it.
    """

    account_id: int
    account_code: str
    account_name: str
    account_type: str
    normal_balance: str
    debit_total: Decimal
    credit_total: Decimal
    balance: Decimal


@dataclass(frozen=True)
class TrialBalance:
    """The whole trial balance of one organization as of ``as_of``.

    ``as_of`` is ``None`` for an unbounded report, meaning "every posted entry
    so far", which is not the same as a report as of today: an entry dated in
    the future is excluded once a bound is supplied, and included without one.

    ``difference`` is ``debit_total - credit_total``. It is zero when the books
    balance and non-zero when they do not, and it is published either way.
    """

    organization_id: int
    as_of: date | None
    accounts: tuple[TrialBalanceAccount, ...]
    debit_total: Decimal
    credit_total: Decimal
    difference: Decimal

    @property
    def is_balanced(self) -> bool:
        """Whether the posted entries agree.

        Computed from the totals rather than assumed from the fact that every
        entry passed posting validation. The two are not the same claim: a
        posting path that was bypassed, a migration that loaded unbalanced data
        or a bug in the reversal logic all produce an imbalance while every
        individual entry still looked valid when it was written.
        """
        return self.difference == 0


def _account_row(account_ledger: AccountLedger) -> TrialBalanceAccount:
    """One ledger account as a trial balance row.

    The ledger's period totals are the cumulative totals here because
    ``build_trial_balance`` never sets a lower bound. If an opening balance
    ever appeared it would mean the two reports disagreed about what
    "everything posted so far" means, and silently dropping it would hide the
    difference; it is raised instead.
    """
    if account_ledger.opening_balance != money(0):
        raise AssertionError(
            "a trial balance is cumulative: the ledger returned an opening "
            f"balance of {account_ledger.opening_balance} for account "
            f"{account_ledger.account.id}"
        )
    return TrialBalanceAccount(
        account_id=account_ledger.account.id,
        account_code=account_ledger.account.code,
        account_name=account_ledger.account.name,
        account_type=account_ledger.account.account_type,
        normal_balance=account_ledger.account.normal_balance,
        debit_total=account_ledger.period_debit_total,
        credit_total=account_ledger.period_credit_total,
        balance=account_ledger.closing_balance,
    )


def build_trial_balance(
    store: AccountingStore,
    organization_id: int,
    as_of: date | None = None,
) -> TrialBalance:
    """Compute the trial balance of ``organization_id`` as of ``as_of``.

    ``as_of`` is inclusive on ``entry_date``: an entry dated exactly ``as_of``
    is included.

    Only accounts that a posted line actually touches appear. An account with no
    activity is a row of zeros, and :mod:`src.ledger` omits it for the same
    reason; a row of zeros is also a place where a rounding or sign mistake can
    hide.

    Raises:
        src.accounting_store.AccountingError: ``organization_not_found`` when
            the organization is unknown. Nothing else can fail here: there are
            no filters naming another tenant's rows to resolve.
    """
    # No `date_from` is passed, so the ledger has no history before the period:
    # its opening balance is zero for every account and its period totals are
    # already the cumulative figures up to `as_of`. That is asserted below
    # rather than assumed, because the two fields silently becoming different
    # is exactly the bug this projection exists to avoid.
    ledger = build_ledger(store, organization_id, LedgerFilter(date_to=as_of))
    accounts = tuple(
        _account_row(account_ledger) for account_ledger in ledger.accounts
    )
    return TrialBalance(
        organization_id=organization_id,
        as_of=as_of,
        accounts=accounts,
        debit_total=ledger.period_debit_total,
        credit_total=ledger.period_credit_total,
        difference=ledger.net_movement,
    )


def imbalance_details(balance: TrialBalance) -> dict[str, str]:
    """The exact figures behind an imbalance, as decimal strings.

    Used both in the response's ``error.details`` and in the log/audit record,
    so the three always agree character for character. Formatting once here is
    what keeps a log line and a response body from telling an operator two
    slightly different numbers.
    """
    return {
        "organization_id": str(balance.organization_id),
        "as_of": balance.as_of.isoformat() if balance.as_of is not None else "",
        "debit_total": format_money(balance.debit_total),
        "credit_total": format_money(balance.credit_total),
        "difference": format_money(balance.difference),
    }


def unbalanced_error(balance: TrialBalance) -> dict[str, object] | None:
    """The structured error envelope for an imbalance, or ``None`` if balanced.

    The shape is the shared envelope ``{"code", "message", "details"}``, so a
    client reads a failure the same way here as on any other endpoint.

    It is returned *next to* the figures rather than instead of them: the
    operator needs the exact difference to find the offending entry, and a
    response that hid the report would leave them with a code and nothing to
    act on.
    """
    if balance.is_balanced:
        return None
    return {
        "code": TRIAL_BALANCE_UNBALANCED,
        "message": (
            f"posted entries do not balance: debits {format_money(balance.debit_total)} "
            f"vs credits {format_money(balance.credit_total)}, "
            f"difference {format_money(balance.difference)}"
        ),
        "details": imbalance_details(balance),
    }


def trial_balance_to_dict(balance: TrialBalance) -> dict[str, object]:
    """Render a :class:`TrialBalance` as the API's JSON body.

    Every amount is a decimal string (see the module docstring). The ``error``
    key is present only when the books do not balance, so a balanced report has
    no failure in it at all and an imbalanced one cannot be mistaken for a
    clean read.
    """
    body: dict[str, object] = {
        "organization_id": balance.organization_id,
        "as_of": balance.as_of.isoformat() if balance.as_of is not None else None,
        "is_balanced": balance.is_balanced,
        "totals": {
            "debit_total": format_money(balance.debit_total),
            "credit_total": format_money(balance.credit_total),
            "difference": format_money(balance.difference),
        },
        "accounts": [
            {
                "account_id": account.account_id,
                "account_code": account.account_code,
                "account_name": account.account_name,
                "account_type": account.account_type,
                "normal_balance": account.normal_balance,
                "debit_total": format_money(account.debit_total),
                "credit_total": format_money(account.credit_total),
                "balance": format_money(account.balance),
            }
            for account in balance.accounts
        ],
    }
    error = unbalanced_error(balance)
    if error is not None:
        body["error"] = error
    return body


def _default_recorder() -> AuditRecorder | None:
    """The audit service's ``record`` if it is present, else ``None``.

    Imported lazily and defensively because the audit trail lands on a parallel
    branch: a report must keep working when it is not wired yet, and the
    imbalance is still surfaced in the response and in the log regardless.
    """
    try:
        from .audit import record
    except ImportError:
        return None
    return record


def report_imbalance(
    balance: TrialBalance,
    *,
    user_id: int | None = None,
    recorder: AuditRecorder | None = None,
) -> dict[str, str]:
    """Log and audit an unbalanced trial balance. Returns the details recorded.

    Reporting a broken ledger is an event, not a rendering detail: it is the
    one moment in this report where the operator must find out, even if nobody
    ever opens the screen. It goes to the log unconditionally, and to the audit
    trail when the audit service is available.

    A recorder that raises must not take the request down with it — the caller
    still needs the figures, and a failing audit sink is not a licence to hide
    an imbalance. The failure is logged at exception level instead.
    """
    details = imbalance_details(balance)
    logger.warning(
        "trial balance out of balance: code=%s organization_id=%s as_of=%s "
        "debit_total=%s credit_total=%s difference=%s",
        TRIAL_BALANCE_UNBALANCED,
        balance.organization_id,
        balance.as_of.isoformat() if balance.as_of is not None else "-",
        details["debit_total"],
        details["credit_total"],
        details["difference"],
    )
    target = recorder if recorder is not None else _default_recorder()
    if target is not None:
        try:
            target(
                action=AUDIT_ACTION_TRIAL_BALANCE_UNBALANCED,
                entity="trial_balance",
                entity_id=str(balance.organization_id),
                organization_id=balance.organization_id,
                user_id=user_id,
                metadata=details,
            )
        except Exception:
            logger.exception(
                "audit of the unbalanced trial balance failed; the imbalance is "
                "still reported in the response and in the log above"
            )
    return details
