from fastapi import APIRouter, Depends, Request
from .audit import PostgresAuditStore
from .errors import ApiError, ErrorCode
from .error_log_api import require_error_admin
from .identity import Caller

router = APIRouter(prefix="/api/v1/organizations", tags=["management"])

@router.get("/{organization_id}/audit")
def audit(organization_id: int, request: Request, caller: Caller = Depends(require_error_admin)):
    store = request.app.state.audit_store
    rows = store.list_for_organization(organization_id)
    return {"items": [row.to_dict() for row in rows[-500:]]}
