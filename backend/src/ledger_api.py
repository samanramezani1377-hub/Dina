"""The accounting read endpoints: the ledger and the trial balance.

Kept in one module rather than in ``main.py`` so the routes, their request
parsing and their error mapping sit together and can be tested without booting
the whole application. Both reports read the same posted-only source
(:data:`src.models.LEDGER_STATUSES`) through the same dependency, so they cannot
drift apart on which entries count.

Three checks run before any arithmetic, in this order:

1. **Authentication.** No caller identity, no response. See :mod:`src.identity`.
2. **Membership.** A caller who is not a member of the requested organization
   is refused. This is also the tenant boundary: an organization id in the path
   names which rows are readable, and there is no path to another tenant's.
3. **Permission.** The role must rank at or above ``accountant``
   (:mod:`src.permissions`). A ``viewer`` may look at a dashboard; a full
   ledger of every account is above that.

Domain failures (``account_not_found``, ``journal_not_found``) map to 404 and
permission failures to 403. A cross-tenant id is answered with 404 rather than
403 so a caller cannot probe for which ids exist in other organizations. Every
one of them leaves through the envelope defined in :mod:`src.errors`; nothing
here builds a response by hand.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from .accounting_store import AccountingStore
from .errors import ApiError, ErrorCode
from .identity import Caller, current_user_id, resolve_caller
from .ledger import LedgerFilter, build_ledger, ledger_to_dict
from .permissions import ACCOUNTING_ROLE, has_role
from .store import InMemoryStore
from .trial_balance import build_trial_balance, report_imbalance, trial_balance_to_dict

router = APIRouter(prefix="/api/v1/organizations", tags=["accounting"])


def get_accounting_store(request: Request) -> AccountingStore:
    """The process-wide accounting store, attached during startup."""
    return request.app.state.accounting_store


def get_memberships(request: Request) -> InMemoryStore:
    """The process-wide organization/membership store."""
    return request.app.state.memberships


def require_accounting_caller(
    organization_id: int,
    user_id: int = Depends(current_user_id),
    memberships: InMemoryStore = Depends(get_memberships),
) -> Caller:
    """Authenticate the caller and check membership and role for the org.

    ``organization_id`` is the route's own path parameter, resolved by FastAPI
    before this runs, so the check is bound to the organization that was
    actually requested rather than to one supplied in a body or query string.

    Raises:
        AuthenticationError: 401 when the request carries no usable identity,
            404 when the organization does not exist, 403 when the caller is not
            a member or ranks below ``accountant``.
        ApiError: ``permission_denied`` when the caller's role is too low.
    """
    caller = resolve_caller(user_id, organization_id, memberships)
    if not has_role(caller.role, ACCOUNTING_ROLE):
        raise ApiError(
            ErrorCode.PERMISSION_DENIED,
            f"role {caller.role!r} is below the {ACCOUNTING_ROLE!r} required for "
            "this report",
            {"role": caller.role, "required_role": ACCOUNTING_ROLE},
        )
    return caller


@router.get("/{organization_id}/ledger")
def read_ledger(
    organization_id: int,
    caller: Caller = Depends(require_accounting_caller),
    accounting_store: AccountingStore = Depends(get_accounting_store),
    account_id: int | None = Query(
        default=None, description="Restrict the report to one account of this organization."
    ),
    date_from: date | None = Query(
        default=None, description="Inclusive first day of the period."
    ),
    date_to: date | None = Query(default=None, description="Inclusive last day of the period."),
    entry_id: int | None = Query(
        default=None, description="Restrict the report to one journal entry."
    ),
    document_no: str | None = Query(
        default=None, description="Restrict the report to one document number."
    ),
) -> dict[str, object]:
    """Return the general ledger of one organization.

    Only ``posted`` and ``reversed`` entries are included; a draft never
    appears. Amounts are exact decimal strings. An organization with nothing
    posted returns an empty report with zero totals, not an error.
    """
    ledger_filter = LedgerFilter(
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        entry_id=entry_id,
        document_no=document_no,
    )
    # A domain failure needs no translation here any more: AccountingError is an
    # ApiError, so the code it already carries is the code that goes on the wire.
    ledger = build_ledger(accounting_store, organization_id, ledger_filter)
    return ledger_to_dict(ledger)


@router.get("/{organization_id}/trial-balance")
def read_trial_balance(
    organization_id: int,
    caller: Caller = Depends(require_accounting_caller),
    accounting_store: AccountingStore = Depends(get_accounting_store),
    as_of: date | None = Query(
        default=None,
        description=(
            "Inclusive last day to report on. Omit it for every posted entry "
            "so far, which is not the same as a report as of today."
        ),
    ),
) -> dict[str, object]:
    """Return the trial balance of one organization.

    Cumulative rather than per-period: without a lower bound, each account
    carries every posted entry up to ``as_of`` on each side, plus the signed
    net balance. Amounts are exact decimal strings.

    An organization whose entries do not balance still gets its figures. The
    response is 200 with ``is_balanced: false``, the exact ``difference`` and a
    structured ``error`` carrying :data:`src.trial_balance.
    TRIAL_BALANCE_UNBALANCED`; the difference is logged and audited on the way
    out. The report is never adjusted to look balanced — see
    :mod:`src.trial_balance`.
    """
    balance = build_trial_balance(accounting_store, organization_id, as_of)
    if not balance.is_balanced:
        report_imbalance(balance, user_id=caller.user_id)
    return trial_balance_to_dict(balance)