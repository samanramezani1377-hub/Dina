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

from fastapi import FastAPI
from pydantic import BaseModel

from .accounting import validate_journal
from .accounting_store import AccountingStore
from .auth import UserDirectory
from .auth_api import router as auth_router
from .config import get_settings
from .errors import register_error_handlers
from .ledger_api import router as ledger_router
from .models import JournalLine
from .store import InMemoryStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading settings here is the fail-fast gate: a missing or blank
    # SECRET_KEY raises ConfigurationError and the process refuses to serve.
    app.state.settings = get_settings()
    # TODO(persistence): replace all three stores with the PostgreSQL
    # repositories once the migrations in database/migrations are wired up. They
    # are created here rather than at import time so a test can swap an isolated
    # instance in before any request is served.
    app.state.memberships = InMemoryStore({}, [])
    app.state.accounting_store = AccountingStore()
    app.state.users = UserDirectory()
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
def validate(payload: JournalInput) -> dict[str, object]:
    """Check a journal's arithmetic without storing anything.

    The route deliberately adds no tenant check of its own: it performs no read
    and no write, so it cannot leak another organization's data. The audit
    wiring that the append-only audit service needs is not present on this
    branch and is restored by the landing bead.

    A journal that breaks a rule is answered with the rule's own code —
    ``journal_empty``, ``amount_must_be_non_negative``,
    ``line_must_have_exactly_one_side`` or ``journal_not_balanced`` — in the
    envelope, with the figures that failed in ``details``. The exception raised
    by :func:`src.accounting.validate_journal` is already coded, so there is
    nothing here to catch and re-shape.
    """
    validate_journal([JournalLine(**line.model_dump()) for line in payload.lines])
    return {
        "valid": True,
        "organization_id": payload.organization_id,
        "document_no": payload.document_no,
        "description": payload.description,
        "lines": len(payload.lines),
    }
