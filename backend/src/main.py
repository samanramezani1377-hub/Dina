from fastapi import FastAPI,HTTPException,Request
from pydantic import BaseModel
from decimal import Decimal
from .accounting import validate_journal
from .audit import AuditAction, record
from .models import JournalLine
app=FastAPI(title="Dina API",version="0.2.0")
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
def validate(payload:JournalInput,request:Request=None):
    try: validate_journal([JournalLine(**x.model_dump()) for x in payload.lines])
    except ValueError as e:
        code=str(e)
        # Rejected journal attempts are audited against the tenant they claimed.
        record(action=AuditAction.JOURNAL_CREATED,entity="journal_entry",entity_id=None,organization_id=payload.organization_id,metadata={"document_no":payload.document_no,"outcome":"rejected","reason_code":code,"line_count":len(payload.lines)},correlation_id=_correlation_id(request),ip_address=_ip_address(request))
        raise HTTPException(422,detail=code) from e
    record(action=AuditAction.JOURNAL_CREATED,entity="journal_entry",entity_id=None,organization_id=payload.organization_id,metadata={"document_no":payload.document_no,"outcome":"validated","line_count":len(payload.lines)},correlation_id=_correlation_id(request),ip_address=_ip_address(request))
    return {"valid":True,"organization_id":payload.organization_id,"document_no":payload.document_no,"description":payload.description,"lines":len(payload.lines)}

def _correlation_id(request:Request|None)->str|None:
    if request is None: return None
    value=request.headers.get('x-request-id') or request.headers.get('x-correlation-id')
    return str(value) if value else None

def _ip_address(request:Request|None)->str|None:
    if request is None or not hasattr(request,'client') or request.client is None: return None
    return request.client.host
