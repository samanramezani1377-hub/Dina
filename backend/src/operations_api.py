from __future__ import annotations
"""Authenticated operational accounting and SaaS API."""
from datetime import date, datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from .auth import token_user_id
from .errors import ApiError, ErrorCode
from .identity import Caller, resolve_caller
from .permissions import ACCOUNTING_ROLE, has_role
from .audit import AuditAction, record
from .models import JournalLine
from .business_store import BusinessStore

router = APIRouter(prefix="/api/v1", tags=["operations"])

ROLES = {"owner","manager","accountant","sales","inventory","viewer"}

def _caller(request: Request, organization_id: int, user_id: int, minimum: str = "viewer") -> Caller:
    caller = resolve_caller(user_id, organization_id, request.app.state.memberships)
    if not has_role(caller.role, minimum):
        raise ApiError(ErrorCode.PERMISSION_DENIED, "insufficient role", {"role": caller.role, "required_role": minimum})
    return caller

def accounting_caller(
    organization_id: int,
    request: Request,
    user_id: int = Depends(token_user_id),
) -> Caller:
    return _caller(request, organization_id, user_id, ACCOUNTING_ROLE)

def member_caller(
    organization_id: int,
    request: Request,
    user_id: int = Depends(token_user_id),
) -> Caller:
    return _caller(request, organization_id, user_id)

def _json(value):
    if isinstance(value, Decimal): return str(value)
    if hasattr(value, "isoformat"): return value.isoformat()
    if isinstance(value, dict): return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_json(v) for v in value]
    return value

class OrganizationInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
class AccountInput(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    account_type: str
class LineInput(BaseModel):
    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
class JournalInput(BaseModel):
    document_no: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=1000)
    entry_date: date
    lines: list[LineInput] = Field(min_length=1)
class JournalPatch(BaseModel):
    description: str | None = Field(default=None, max_length=1000)
    entry_date: date | None = None
    lines: list[LineInput] | None = None
class CustomerInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
class InvoiceInput(BaseModel):
    customer_id: int
    invoice_no: str = Field(min_length=1, max_length=100)
    total: Decimal = Field(ge=0)
    issue_date: date
    due_date: date | None = None
class PaymentInput(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = Field(default="other", max_length=50)
    reference: str | None = Field(default=None, max_length=200)
class SubscriptionInput(BaseModel):
    plan: str = Field(min_length=1, max_length=100)
    status: str = "active"
    starts_at: datetime | None = None
    ends_at: datetime | None = None

@router.post("/organizations", status_code=201)
def create_organization(payload: OrganizationInput, request: Request, user_id: int = Depends(token_user_id)):
    org = request.app.state.memberships.create_organization(payload.name, user_id)
    record(action=AuditAction.ORGANIZATION_CREATED, entity="organization", entity_id=org.id,
           user_id=user_id, organization_id=org.id, metadata={"name": org.name})
    return {"id": org.id, "name": org.name}

@router.post("/organizations/{organization_id}/members", status_code=204)
def add_member(organization_id: int, member_user_id: int, role: str, request: Request,
               caller: Caller = Depends(accounting_caller)):
    if role not in ROLES:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "invalid role")
    try:
        request.app.state.memberships.add_membership(member_user_id, organization_id, role)
    except ValueError as exc:
        raise ApiError(ErrorCode.ORGANIZATION_NOT_FOUND, str(exc)) from exc
    record(action=AuditAction.MEMBERSHIP_ADDED, entity="membership",
           entity_id=f"{member_user_id}:{organization_id}", user_id=caller.user_id,
           organization_id=organization_id, metadata={"member_user_id": member_user_id, "role": role})

@router.delete("/organizations/{organization_id}/members/{member_user_id}", status_code=204)
def remove_member(organization_id: int, member_user_id: int, request: Request,
                  caller: Caller = Depends(accounting_caller)):
    request.app.state.memberships.remove_membership(member_user_id, organization_id)
    record(action=AuditAction.MEMBERSHIP_REMOVED, entity="membership",
           entity_id=f"{member_user_id}:{organization_id}", user_id=caller.user_id,
           organization_id=organization_id, metadata={"member_user_id": member_user_id})

@router.post("/organizations/{organization_id}/accounts", status_code=201)
def create_account(organization_id: int, payload: AccountInput, request: Request,
                   caller: Caller = Depends(accounting_caller)):
    account = request.app.state.accounting_store.add_account(
        organization_id, payload.code, payload.name, payload.account_type
    )
    record(action=AuditAction.ACCOUNT_CREATED, entity="account", entity_id=account.id,
           user_id=caller.user_id, organization_id=organization_id,
           metadata={"code": account.code, "name": account.name, "account_type": account.account_type})
    return _json(account.__dict__)

@router.get("/organizations/{organization_id}/accounts")
def list_accounts(organization_id: int, request: Request,
                  caller: Caller = Depends(accounting_caller)):
    return {"items": [_json(a.__dict__) for a in request.app.state.accounting_store.list_accounts(organization_id)]}

@router.post("/organizations/{organization_id}/journals", status_code=201)
def create_journal(organization_id: int, payload: JournalInput, request: Request,
                   caller: Caller = Depends(accounting_caller)):
    lines = [JournalLine(x.account_id, x.debit, x.credit) for x in payload.lines]
    entry = request.app.state.accounting_store.add_entry(
        organization_id, payload.document_no, payload.description, payload.entry_date, lines
    )
    record(action=AuditAction.JOURNAL_CREATED, entity="journal_entry", entity_id=entry.id,
           user_id=caller.user_id, organization_id=organization_id,
           metadata={"document_no": entry.document_no, "status": entry.status})
    return _json(entry.__dict__)

@router.get("/organizations/{organization_id}/journals/{entry_id}")
def get_journal(organization_id: int, entry_id: int, request: Request,
                caller: Caller = Depends(accounting_caller)):
    return _json(request.app.state.accounting_store.get_entry(organization_id, entry_id).__dict__)

@router.post("/organizations/{organization_id}/journals/{entry_id}/post")
def post_journal(organization_id: int, entry_id: int, request: Request,
                 caller: Caller = Depends(accounting_caller)):
    entry = request.app.state.accounting_store.post_entry(organization_id, entry_id)
    record(action=AuditAction.JOURNAL_POSTED, entity="journal_entry", entity_id=entry.id,
           user_id=caller.user_id, organization_id=organization_id)
    return _json(entry.__dict__)

@router.post("/organizations/{organization_id}/journals/{entry_id}/reverse")
def reverse_journal(organization_id: int, entry_id: int, document_no: str, entry_date: date,
                    request: Request, description: str = "",
                    caller: Caller = Depends(accounting_caller)):
    entry = request.app.state.accounting_store.reverse_entry(
        organization_id, entry_id, document_no, entry_date, description
    )
    record(action=AuditAction.JOURNAL_REVERSED, entity="journal_entry", entity_id=entry.id,
           user_id=caller.user_id, organization_id=organization_id,
           metadata={"reversal_of": entry.reversal_of_entry_id})
    return _json(entry.__dict__)

@router.patch("/organizations/{organization_id}/journals/{entry_id}")
def patch_journal(organization_id: int, entry_id: int, payload: JournalPatch, request: Request,
                  caller: Caller = Depends(accounting_caller)):
    lines = None if payload.lines is None else [JournalLine(x.account_id, x.debit, x.credit) for x in payload.lines]
    entry = request.app.state.accounting_store.update_entry(
        organization_id, entry_id, description=payload.description, entry_date=payload.entry_date, lines=lines
    )
    record(action=AuditAction.JOURNAL_CORRECTED, entity="journal_entry", entity_id=entry.id,
           user_id=caller.user_id, organization_id=organization_id)
    return _json(entry.__dict__)

@router.delete("/organizations/{organization_id}/journals/{entry_id}", status_code=204)
def delete_journal(organization_id: int, entry_id: int, request: Request,
                   caller: Caller = Depends(accounting_caller)):
    request.app.state.accounting_store.delete_entry(organization_id, entry_id)

@router.post("/organizations/{organization_id}/customers", status_code=201)
def create_customer(organization_id: int, payload: CustomerInput, request: Request,
                    caller: Caller = Depends(member_caller)):
    return _json(request.app.state.business_store.create_customer(
        organization_id, payload.name, payload.email, payload.phone
    ))

@router.get("/organizations/{organization_id}/customers")
def list_customers(organization_id: int, request: Request,
                   caller: Caller = Depends(member_caller)):
    return {"items": _json(request.app.state.business_store.list_customers(organization_id))}

@router.post("/organizations/{organization_id}/invoices", status_code=201)
def create_invoice(organization_id: int, payload: InvoiceInput, request: Request,
                   caller: Caller = Depends(member_caller)):
    try:
        invoice = request.app.state.business_store.create_invoice(
            organization_id, payload.customer_id, payload.invoice_no, payload.total,
            payload.issue_date, payload.due_date
        )
    except KeyError as exc:
        raise ApiError(ErrorCode.NOT_FOUND, "customer does not exist in this organization") from exc
    return _json(invoice)

@router.get("/organizations/{organization_id}/invoices")
def list_invoices(organization_id: int, request: Request,
                  caller: Caller = Depends(member_caller)):
    return {"items": _json(request.app.state.business_store.list_invoices(organization_id))}

@router.post("/organizations/{organization_id}/invoices/{invoice_id}/payments", status_code=201)
def pay_invoice(organization_id: int, invoice_id: int, payload: PaymentInput, request: Request,
                caller: Caller = Depends(accounting_caller)):
    try:
        payment, invoice = request.app.state.business_store.record_payment(
            organization_id, invoice_id, payload.amount, payload.method, payload.reference, request.headers.get('Idempotency-Key')
        )
    except KeyError as exc:
        raise ApiError(ErrorCode.NOT_FOUND, "invoice does not exist in this organization") from exc
    except ValueError as exc:
        raise ApiError(ErrorCode.VALIDATION_ERROR, str(exc)) from exc
    record(action=AuditAction.PAYMENT_RECORDED, entity="payment", entity_id=payment["id"],
           user_id=caller.user_id, organization_id=organization_id,
           metadata={"invoice_id": invoice_id, "amount": payload.amount})
    return {"payment": _json(payment), "invoice": _json(invoice)}

@router.put("/organizations/{organization_id}/subscription")
def set_subscription(organization_id: int, payload: SubscriptionInput, request: Request,
                     caller: Caller = Depends(accounting_caller)):
    allowed = {"trial","active","past_due","cancelled","expired"}
    if payload.status not in allowed:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "invalid subscription status")
    subscription = request.app.state.business_store.upsert_subscription(
        organization_id, payload.plan, payload.status,
        payload.starts_at or datetime.now(timezone.utc), payload.ends_at
    )
    record(action=AuditAction.SUBSCRIPTION_CHANGED, entity="subscription", entity_id=subscription["id"],
           user_id=caller.user_id, organization_id=organization_id,
           metadata={"plan": payload.plan, "status": payload.status})
    return _json(subscription)

@router.get("/organizations/{organization_id}/subscription")
def get_subscription(organization_id: int, request: Request,
                      caller: Caller = Depends(member_caller)):
    return {"subscription": _json(request.app.state.business_store.subscription(organization_id))}
