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
    # TODO(auth): this route has no authentication yet, so the tenant cannot be
    # resolved server-side. The body's organization_id is a client claim and
    # MUST NOT be trusted: it is recorded under a non-tenant key only. When
    # JWT/RBAC lands, resolve the organization from the membership dependency
    # and ignore the body field entirely.
    def audit_details(outcome:str,**extra):
        return {"document_no":payload.document_no,"outcome":outcome,"line_count":len(payload.lines),"claimed_organization_id":payload.organization_id,**extra}
    try: validate_journal([JournalLine(**x.model_dump()) for x in payload.lines])
    except ValueError as e:
        code=str(e)
        record(action=AuditAction.JOURNAL_CREATED,entity="journal_entry",entity_id=None,organization_id=None,metadata=audit_details("rejected",reason_code=code),correlation_id=_correlation_id(request),ip_address=_ip_address(request))
        raise HTTPException(422,detail=code) from e
    record(action=AuditAction.JOURNAL_CREATED,entity="journal_entry",entity_id=None,organization_id=None,metadata=audit_details("validated"),correlation_id=_correlation_id(request),ip_address=_ip_address(request))
    return {"valid":True,"organization_id":payload.organization_id,"document_no":payload.document_no,"description":payload.description,"lines":len(payload.lines)}

def _correlation_id(request:Request|None)->str|None:
    if request is None: return None
    value=request.headers.get('x-request-id') or request.headers.get('x-correlation-id')
    return str(value) if value else None

def _ip_address(request:Request|None)->str|None:
    if request is None or not hasattr(request,'client') or request.client is None: return None
    return request.client.host
