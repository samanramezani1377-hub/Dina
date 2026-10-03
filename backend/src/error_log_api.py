from fastapi import APIRouter, Depends, Request
from .error_log import list_errors, resolve_error
from .errors import ApiError, ErrorCode
from .identity import Caller, current_user_id, resolve_caller
from .ledger_api import get_memberships
from .permissions import has_role

router = APIRouter(prefix="/api/v1/organizations", tags=["error-center"])
_ALLOWED_ROLES = {"owner", "manager"}

def require_error_admin(organization_id: int, request: Request, user_id: int = Depends(current_user_id)) -> Caller:
    caller = resolve_caller(user_id, organization_id, get_memberships(request))
    if caller.role not in _ALLOWED_ROLES:
        raise ApiError(ErrorCode.PERMISSION_DENIED, "only organization owners and managers can access the error center",
                       {"required_roles": sorted(_ALLOWED_ROLES), "role": caller.role})
    return caller

@router.get("/{organization_id}/errors")
def errors(organization_id: int, request: Request, caller: Caller = Depends(require_error_admin),
           limit: int = 100, offset: int = 0, code: str | None = None,
           unresolved_only: bool = False):
    settings = request.app.state.settings
    return {"items": list_errors(settings.database_url, limit=limit, offset=offset,
                                  code=code, unresolved_only=unresolved_only)}

@router.post("/{organization_id}/errors/{error_id}/resolve")
def resolve(organization_id: int, error_id: int, request: Request,
            caller: Caller = Depends(require_error_admin)):
    ok = resolve_error(request.app.state.settings.database_url, error_id, caller.user_id)
    if not ok:
        raise ApiError(ErrorCode.NOT_FOUND, "error log was not found or is already resolved",
                       {"error_id": error_id})
    return {"resolved": True, "error_id": error_id}
