from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
from decimal import Decimal
from .accounting import validate_journal
from .config import get_settings
from .models import JournalLine
@asynccontextmanager
async def lifespan(app:FastAPI):
    # Loading settings here is the fail-fast gate: a missing or blank
    # SECRET_KEY raises ConfigurationError and the process refuses to serve.
    app.state.settings=get_settings()
    yield
app=FastAPI(title="Dina API",version="0.2.0",lifespan=lifespan)
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
