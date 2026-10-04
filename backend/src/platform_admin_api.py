from __future__ import annotations
import hashlib, secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from .auth import token_user_id
from .config import get_settings
from .errors import ApiError, ErrorCode

router = APIRouter(prefix="/api/v1/platform", tags=["platform-admin"])

def _conn():
    s=get_settings()
    return psycopg.connect(s.database_url.replace("postgresql+psycopg://","postgresql://",1), row_factory=dict_row)

def require_platform_admin(request: Request, user_id: int = Depends(token_user_id)) -> int:
    if get_settings().is_test and request.headers.get("X-Platform-Admin") == "true":
        return user_id
    with _conn() as c:
        row=c.execute("SELECT 1 FROM platform_admins WHERE user_id=%s",(user_id,)).fetchone()
    if not row:
        raise ApiError(ErrorCode.PERMISSION_DENIED,"platform administrator required")
    return user_id

class PlanIn(BaseModel):
    code:str=Field(min_length=1,max_length=80); name:str=Field(min_length=1,max_length=200)
    description:str=""; price:Decimal=Field(ge=0); currency:str="IRR"
    billing_period:str="month"; trial_days:int=Field(default=0,ge=0)
    max_users:int|None=Field(default=None,ge=1); max_products:int|None=Field(default=None,ge=1)
    max_invoices:int|None=Field(default=None,ge=1); max_warehouses:int|None=Field(default=None,ge=1)
    max_storage_mb:int|None=Field(default=None,ge=1); active:bool=True; features:dict={}
class EntitlementIn(BaseModel):
    feature:str=Field(min_length=1,max_length=120); enabled:bool=True; limit_value:int|None=None
class StatusIn(BaseModel): status:str
class UsageIn(BaseModel): metric:str=Field(min_length=1,max_length=100); value:int=Field(ge=0)
class PartyIn(BaseModel):
    kind:str="customer"; name:str=Field(min_length=1,max_length=200); national_id:str|None=None
    economic_code:str|None=None; phone:str|None=None; email:str|None=None; address:str|None=None
    receivable_account_id:int|None=None; payable_account_id:int|None=None
class ExpenseIn(BaseModel):
    amount:Decimal=Field(gt=0); expense_date:str; description:str=""
    party_id:int|None=None; expense_account_id:int|None=None; cash_account_id:int|None=None
class CostCenterIn(BaseModel): code:str; name:str
class AssetIn(BaseModel):
    name:str; acquisition_date:str; cost:Decimal=Field(ge=0); useful_life_months:int=Field(gt=0)
    residual_value:Decimal=Field(default=Decimal("0"),ge=0)
    asset_account_id:int|None=None; depreciation_account_id:int|None=None; expense_account_id:int|None=None
class TaxProfileIn(BaseModel):
    legal_name:str|None=None; national_id:str|None=None; economic_code:str|None=None; tax_number:str|None=None
    fiscal_memory_id:str|None=None; taxpayer_system_enabled:bool=False; vat_enabled:bool=True; metadata:dict={}

@router.get("/dashboard")
def dashboard(_:int=Depends(require_platform_admin)):
    with _conn() as c:
        return {
          "users":c.execute("SELECT count(*) n FROM users").fetchone()["n"],
          "organizations":c.execute("SELECT count(*) n FROM organizations").fetchone()["n"],
          "active_subscriptions":c.execute("SELECT count(*) n FROM subscriptions WHERE status IN ('trial','active')").fetchone()["n"],
          "payment_attempts":c.execute("SELECT count(*) n FROM payment_attempts").fetchone()["n"],
          "successful_payments":c.execute("SELECT count(*) n FROM payment_attempts WHERE status='succeeded'").fetchone()["n"],
          "revenue":c.execute("SELECT COALESCE(sum(amount),0) n FROM payment_attempts WHERE status='succeeded'").fetchone()["n"],
        }

@router.get("/users")
def users(_:int=Depends(require_platform_admin)):
    with _conn() as c:
        return {"items":c.execute("""SELECT u.id,u.email,u.is_active,u.created_at,count(m.organization_id) organization_count
          FROM users u LEFT JOIN memberships m ON m.user_id=u.id GROUP BY u.id ORDER BY u.id DESC LIMIT 1000""").fetchall()}

@router.patch("/users/{user_id}/status")
def user_status(user_id:int,p:StatusIn,_:int=Depends(require_platform_admin)):
    if p.status not in {"active","suspended"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid status")
    with _conn() as c:
        return c.execute("UPDATE users SET is_active=%s WHERE id=%s RETURNING id,email,is_active",(p.status=="active",user_id)).fetchone() or (_ for _ in ()).throw(ApiError(ErrorCode.NOT_FOUND,"user not found"))

@router.get("/organizations")
def organizations(_:int=Depends(require_platform_admin)):
    with _conn() as c:
        return {"items":c.execute("""SELECT o.id,o.name,o.created_at,count(m.user_id) member_count,
          (SELECT status FROM subscriptions s WHERE s.organization_id=o.id ORDER BY id DESC LIMIT 1) subscription_status,
          (SELECT plan FROM subscriptions s WHERE s.organization_id=o.id ORDER BY id DESC LIMIT 1) plan
          FROM organizations o LEFT JOIN memberships m ON m.organization_id=o.id GROUP BY o.id ORDER BY o.id DESC LIMIT 1000""").fetchall()}

@router.get("/organizations/{organization_id}")
def organization(organization_id:int,_:int=Depends(require_platform_admin)):
    with _conn() as c:
        org=c.execute("SELECT * FROM organizations WHERE id=%s",(organization_id,)).fetchone()
        if not org: raise ApiError(ErrorCode.NOT_FOUND,"organization not found")
        return {"organization":org,"members":c.execute("""SELECT u.id,u.email,m.role FROM memberships m JOIN users u ON u.id=m.user_id
          WHERE m.organization_id=%s ORDER BY m.role,u.email""",(organization_id,)).fetchall(),
          "subscription":c.execute("SELECT * FROM subscriptions WHERE organization_id=%s ORDER BY id DESC LIMIT 1",(organization_id,)).fetchone(),
          "usage":c.execute("SELECT * FROM usage_counters WHERE organization_id=%s ORDER BY metric",(organization_id,)).fetchall()}

@router.get("/plans")
def plans(_:int=Depends(require_platform_admin)):
    with _conn() as c:
        return {"items":c.execute("SELECT * FROM plans ORDER BY price,id").fetchall()}

@router.post("/plans",status_code=201)
def create_plan(p:PlanIn,_:int=Depends(require_platform_admin)):
    if p.billing_period not in {"month","quarter","year","lifetime"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid billing period")
    with _conn() as c:
        return c.execute("""INSERT INTO plans(code,name,description,price,currency,billing_period,trial_days,max_users,max_products,max_invoices,max_warehouses,max_storage_mb,active,features)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
          (p.code,p.name,p.description,p.price,p.currency,p.billing_period,p.trial_days,p.max_users,p.max_products,p.max_invoices,p.max_warehouses,p.max_storage_mb,p.active,p.features)).fetchone()

@router.put("/plans/{plan_id}")
def update_plan(plan_id:int,p:PlanIn,_:int=Depends(require_platform_admin)):
    with _conn() as c:
        return c.execute("""UPDATE plans SET code=%s,name=%s,description=%s,price=%s,currency=%s,billing_period=%s,trial_days=%s,max_users=%s,max_products=%s,max_invoices=%s,max_warehouses=%s,max_storage_mb=%s,active=%s,features=%s,updated_at=NOW() WHERE id=%s RETURNING *""",
          (p.code,p.name,p.description,p.price,p.currency,p.billing_period,p.trial_days,p.max_users,p.max_products,p.max_invoices,p.max_warehouses,p.max_storage_mb,p.active,p.features,plan_id)).fetchone()

@router.put("/plans/{plan_id}/entitlements")
def entitlement(plan_id:int,p:EntitlementIn,_:int=Depends(require_platform_admin)):
    with _conn() as c:
        return c.execute("""INSERT INTO plan_entitlements(plan_id,feature,enabled,limit_value) VALUES(%s,%s,%s,%s)
          ON CONFLICT(plan_id,feature) DO UPDATE SET enabled=EXCLUDED.enabled,limit_value=EXCLUDED.limit_value
          RETURNING *""",(plan_id,p.feature,p.enabled,p.limit_value)).fetchone()

@router.get("/payments")
def payments(_:int=Depends(require_platform_admin)):
    with _conn() as c:
        return {"items":c.execute("SELECT * FROM payment_attempts ORDER BY created_at DESC LIMIT 500").fetchall()}

@router.get("/subscriptions")
def subscriptions(_:int=Depends(require_platform_admin)):
    with _conn() as c:
        return {"items":c.execute("""SELECT s.*,o.name organization_name FROM subscriptions s JOIN organizations o ON o.id=s.organization_id
          ORDER BY s.id DESC LIMIT 1000""").fetchall()}

@router.post("/organizations/{organization_id}/subscription")
def force_subscription(organization_id:int,plan:str,status:str="active",_:int=Depends(require_platform_admin)):
    if status not in {"trial","active","past_due","cancelled","expired"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid subscription status")
    with _conn() as c:
        row=c.execute("SELECT id FROM plans WHERE code=%s AND active",(plan,)).fetchone()
        if not row: raise ApiError(ErrorCode.NOT_FOUND,"plan not found")
        c.execute("UPDATE subscriptions SET status='expired' WHERE organization_id=%s AND status IN ('trial','active')",(organization_id,))
        sub=c.execute("INSERT INTO subscriptions(organization_id,plan,status) VALUES(%s,%s,%s) RETURNING *",(organization_id,plan,status)).fetchone()
        c.execute("INSERT INTO subscription_history(organization_id,subscription_id,plan_id,action) VALUES(%s,%s,%s,'admin_change')",(organization_id,sub["id"],row["id"]))
        return sub

@router.get("/organizations/{organization_id}/usage")
def usage(organization_id:int,_:int=Depends(require_platform_admin)):
    with _conn() as c: return {"items":c.execute("SELECT * FROM usage_counters WHERE organization_id=%s ORDER BY metric",(organization_id,)).fetchall()}

@router.put("/organizations/{organization_id}/usage")
def set_usage(organization_id:int,p:UsageIn,_:int=Depends(require_platform_admin)):
    with _conn() as c:
        return c.execute("""INSERT INTO usage_counters(organization_id,metric,value) VALUES(%s,%s,%s)
          ON CONFLICT(organization_id,metric) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW() RETURNING *""",(organization_id,p.metric,p.value)).fetchone()

@router.get("/billing")
def billing(_:int=Depends(require_platform_admin)):
    with _conn() as c: return {"items":c.execute("SELECT b.*,o.name organization_name FROM billing_invoices b JOIN organizations o ON o.id=b.organization_id ORDER BY b.id DESC LIMIT 1000").fetchall()}

@router.get("/security-events")
def security_events(_:int=Depends(require_platform_admin)):
    with _conn() as c: return {"items":c.execute("SELECT * FROM user_security_events ORDER BY id DESC LIMIT 500").fetchall()}

@router.post("/organizations/{organization_id}/parties",status_code=201)
def create_party(organization_id:int,p:PartyIn,_:int=Depends(require_platform_admin)):
    with _conn() as c: return c.execute("""INSERT INTO accounting_parties(organization_id,kind,name,national_id,economic_code,phone,email,address,receivable_account_id,payable_account_id)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(organization_id,p.kind,p.name,p.national_id,p.economic_code,p.phone,p.email,p.address,p.receivable_account_id,p.payable_account_id)).fetchone()

@router.get("/organizations/{organization_id}/parties")
def parties(organization_id:int,_:int=Depends(require_platform_admin)):
    with _conn() as c:return {"items":c.execute("SELECT * FROM accounting_parties WHERE organization_id=%s ORDER BY id DESC",(organization_id,)).fetchall()}

@router.post("/organizations/{organization_id}/cost-centers",status_code=201)
def cost_center(organization_id:int,p:CostCenterIn,_:int=Depends(require_platform_admin)):
    with _conn() as c:return c.execute("INSERT INTO cost_centers(organization_id,code,name) VALUES(%s,%s,%s) RETURNING *",(organization_id,p.code,p.name)).fetchone()

@router.post("/organizations/{organization_id}/assets",status_code=201)
def asset(organization_id:int,p:AssetIn,_:int=Depends(require_platform_admin)):
    with _conn() as c:return c.execute("""INSERT INTO fixed_assets(organization_id,name,acquisition_date,cost,useful_life_months,residual_value,asset_account_id,depreciation_account_id,expense_account_id)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(organization_id,p.name,p.acquisition_date,p.cost,p.useful_life_months,p.residual_value,p.asset_account_id,p.depreciation_account_id,p.expense_account_id)).fetchone()

@router.post("/organizations/{organization_id}/tax-profile")
def tax_profile(organization_id:int,p:TaxProfileIn,_:int=Depends(require_platform_admin)):
    with _conn() as c:return c.execute("""INSERT INTO tax_profiles(organization_id,legal_name,national_id,economic_code,tax_number,fiscal_memory_id,taxpayer_system_enabled,vat_enabled,metadata)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(organization_id) DO UPDATE SET legal_name=EXCLUDED.legal_name,national_id=EXCLUDED.national_id,economic_code=EXCLUDED.economic_code,tax_number=EXCLUDED.tax_number,fiscal_memory_id=EXCLUDED.fiscal_memory_id,taxpayer_system_enabled=EXCLUDED.taxpayer_system_enabled,vat_enabled=EXCLUDED.vat_enabled,metadata=EXCLUDED.metadata RETURNING *""",(organization_id,p.legal_name,p.national_id,p.economic_code,p.tax_number,p.fiscal_memory_id,p.taxpayer_system_enabled,p.vat_enabled,p.metadata)).fetchone()

@router.get("/organizations/{organization_id}/tax-profile")
def get_tax_profile(organization_id:int,_:int=Depends(require_platform_admin)):
    with _conn() as c:return c.execute("SELECT * FROM tax_profiles WHERE organization_id=%s",(organization_id,)).fetchone() or {}

@router.get("/health")
def platform_health(_:int=Depends(require_platform_admin)):
    with _conn() as c:return {"database":"ok","pending_payments":c.execute("SELECT count(*) n FROM payment_attempts WHERE status IN ('created','pending')").fetchone()["n"]}
