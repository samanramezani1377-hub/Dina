"""The Dina API application: routes, state and the error contract.

Three things happen here and nowhere else. The **lifespan** loads settings —
a missing or blank ``SECRET_KEY`` raises and the process refuses to serve —
and builds the stores a request reads. The **routers** are mounted under
``/api/v1``. The **error handlers** are registered, so that every failure the
service reports leaves through one envelope (``src.errors``) instead of FastAPI's
default ``{"detail": ...}``.

The validation route is the smallest complete example of the contract: it
accepts a journal, asks :mod:`src.accounting` whether it is a legal journal, and
answers with the code the rule refused it by. Nothing it returns or raises
contains a Python exception's text.
"""

from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, Request
from pydantic import BaseModel

from .accounting import validate_journal
from .accounting_store import AccountingStore
from .audit import AuditAction, record
from .auth import UserDirectory
from .auth_api import router as auth_router
from .config import get_settings
from .errors import ApiError, register_error_handlers
from .ledger_api import router as ledger_router
from .models import JournalLine
from .postgres_store import PostgresStore
from .store import InMemoryStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading settings here is the fail-fast gate: a missing or blank
    # SECRET_KEY raises ConfigurationError and the process refuses to serve.
    app.state.settings = get_settings()
    # Tests deliberately keep isolated in-memory state. Every other environment
    # uses the PostgreSQL repositories, so a process restart cannot erase users,
    # memberships, accounts or journals.
    if app.state.settings.is_test:
        app.state.memberships = InMemoryStore({}, [])
        app.state.accounting_store = AccountingStore()
        app.state.users = UserDirectory()
    else:
        persistent = PostgresStore(app.state.settings.database_url)
        app.state.memberships = persistent
        app.state.accounting_store = persistent
        app.state.users = persistent
    yield


app = FastAPI(title="Dina API", version="0.3.0", lifespan=lifespan)
app.include_router(ledger_router)
app.include_router(auth_router)
# Handlers are dispatched by exception type at request time, so this can sit
# after the routers without changing which failure goes where.
register_error_handlers(app)


class JournalLineInput(BaseModel):
    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


class JournalInput(BaseModel):
    organization_id: int
    document_no: str
    description: str
    lines: list[JournalLineInput]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "dina-api"}


@app.post("/api/v1/accounting/journals/validate")
def validate(payload: JournalInput, request: Request = None) -> dict[str, object]:
    """Check a journal's arithmetic without storing anything.

    The route deliberately adds no tenant check of its own: it performs no read
    and no write against any organization's data, so it cannot leak another
    tenant's records. Every read of tenant data in this service goes through the
    authenticated routers (``ledger_router``, ``auth_router``), which resolve the
    organization from the caller's membership rather than from a request body.

    A journal that breaks a rule is answered with the rule's own code —
    ``journal_empty``, ``amount_must_be_non_negative``,
    ``line_must_have_exactly_one_side`` or ``journal_not_balanced`` — in the
    envelope, with the figures that failed in ``details``. The exception raised
    by :func:`src.accounting.validate_journal` is already coded, so all this
    route does is record the audit trail and re-raise for
    :mod:`src.errors` to turn into a response.

    **Tenant keying.** The route is unauthenticated, so the body's
    ``organization_id`` is a client claim and MUST NOT be trusted as an
    authorization. The audit row is therefore written with
    ``organization_id=None`` and the claimed id is kept only under the
    non-authoritative ``claimed_organization_id`` key. An anonymous caller can
    never land a row inside another tenant's trail. Once this endpoint is
    placed behind authentication, the organization must be resolved from the
    caller's membership and the body field ignored entirely — see the
    ``TODO(auth)`` above and ``docs/IMPLEMENTATION_STATUS.md``.

    Both outcomes are recorded: a rejected attempt is exactly as auditable as an
    accepted one, which is the point of keeping a trail. ``record`` never
    raises, so an audit-store failure cannot change the answer the client gets.
    """
    details = {
        "document_no": payload.document_no,
        "line_count": len(payload.lines),
        "claimed_organization_id": payload.organization_id,
    }

    try:
        validate_journal([JournalLine(**line.model_dump()) for line in payload.lines])
    except ApiError as exc:
        record(
            action=AuditAction.JOURNAL_CREATED,
            entity="journal_entry",
            entity_id=None,
            organization_id=None,
            metadata={**details, "outcome": "rejected", "reason_code": exc.code},
            correlation_id=_correlation_id(request),
            ip_address=_ip_address(request),
        )
        raise

    record(
        action=AuditAction.JOURNAL_CREATED,
        entity="journal_entry",
        entity_id=None,
        organization_id=None,
        metadata={**details, "outcome": "validated"},
        correlation_id=_correlation_id(request),
        ip_address=_ip_address(request),
    )
    return {
        "valid": True,
        "organization_id": payload.organization_id,
        "document_no": payload.document_no,
        "description": payload.description,
        "lines": len(payload.lines),
    }


def _correlation_id(request: Request | None) -> str | None:
    """The caller's correlation id, or ``None`` when the request is anonymous.

    Deliberately *not* :func:`src.errors.correlation_id`: that helper mints an
    id when the client supplied none, which is the right behaviour for a log
    line but wrong for an audit column — a row should record the id that
    actually arrived, never one this process made up.
    """
    if request is None:
        return None
    value = request.headers.get("x-request-id") or request.headers.get("x-correlation-id")
    return str(value) if value else None


def _ip_address(request: Request | None) -> str | None:
    if request is None or not hasattr(request, "client") or request.client is None:
        return None
    return request.client.host
