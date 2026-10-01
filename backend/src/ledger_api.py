"""The ledger read endpoint.

Kept in its own module rather than in ``main.py`` so the route, its request
parsing and its error mapping sit together and can be tested without booting
the whole application.

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
403 so a caller cannot probe for which ids exist in other organizations.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .accounting_store import AccountingError, AccountingStore
from .identity import AuthenticationError, Caller, current_user_id, resolve_caller
from .ledger import LedgerFilter, build_ledger, ledger_to_dict
from .permissions import ACCOUNTING_ROLE, has_role
from .store import InMemoryStore

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
        HTTPException: 401 when the request carries no usable identity, 404 when
            the organization does not exist, 403 when the caller is not a member
            or ranks below ``accountant``.
    """
    try:
        caller = resolve_caller(user_id, organization_id, memberships)
    except AuthenticationError as exc:
        if exc.code == "organization_not_found":
            raise HTTPException(404, detail=exc.code) from exc
        raise HTTPException(401, detail=exc.code) from exc
    if not has_role(caller.role, ACCOUNTING_ROLE):
        raise HTTPException(403, detail="permission_denied")
    return caller


def _to_http_error(exc: AccountingError) -> HTTPException:
    """Map a domain failure onto a status code.

    ``not_found`` codes become 404 and everything else 422, matching the
    validation endpoint's convention.
    """
    if exc.code.endswith("_not_found"):
        return HTTPException(404, detail=exc.code)
    return HTTPException(422, detail=exc.code)


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
    try:
        ledger = build_ledger(accounting_store, organization_id, ledger_filter)
    except AccountingError as exc:
        raise _to_http_error(exc) from exc
    return ledger_to_dict(ledger)