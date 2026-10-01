from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
from decimal import Decimal
from .accounting import validate_journal
from .accounting_store import AccountingStore
from .config import get_settings
from .ledger_api import router as ledger_router
from .models import JournalLine
from .store import InMemoryStore
@asynccontextmanager
async def lifespan(app:FastAPI):
    # Loading settings here is the fail-fast gate: a missing or blank
    # SECRET_KEY raises ConfigurationError and the process refuses to serve.
    app.state.settings=get_settings()
    # TODO(persistence): replace both stores with the PostgreSQL repositories
    # once the migration in database/migrations is wired up. They are created
    # here rather than at import time so a test can swap an isolated instance
    # in before any request is served.
    app.state.memberships=InMemoryStore({},[])
    app.state.accounting_store=AccountingStore()
    yield
app=FastAPI(title="Dina API",version="0.2.0",lifespan=lifespan)
app.include_router(ledger_router)
class JournalLineInput(BaseModel):
    account_id:int
    debit:Decimal=Decimal("0")
    credit:Decimal=Decimal("0")
class JournalInput(BaseModel):
    organization_id:int
    document_no:str
    description:str
    lines:list[JournalLineInput]
@app.get("/health")
def health(): return {"status":"ok","service":"dina-api"}
@app.post("/api/v1/accounting/journals/validate")
def validate(payload:JournalInput):
    try: validate_journal([JournalLine(**x.model_dump()) for x in payload.lines])
    except ValueError as e: raise HTTPException(422,detail=str(e)) from e
    return {"valid":True,"organization_id":payload.organization_id,"document_no":payload.document_no,"description":payload.description,"lines":len(payload.lines)}
