from __future__ import annotations
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from .auth import token_user_id
from .errors import ApiError, ErrorCode
from .identity import Caller, resolve_caller
from .permissions import has_role

router=APIRouter(prefix="/api/v1/organizations",tags=["business-modules"])

def caller(organization_id:int,request:Request,user_id:int=Depends(token_user_id))->Caller:
    c=resolve_caller(user_id,organization_id,request.app.state.memberships)
    if not has_role(c.role,"viewer"): raise ApiError(ErrorCode.PERMISSION_DENIED,"insufficient role")
    return c
def write_caller(organization_id:int,request:Request,user_id:int=Depends(token_user_id))->Caller:
    c=resolve_caller(user_id,organization_id,request.app.state.memberships)
    if not has_role(c.role,"accountant"): raise ApiError(ErrorCode.PERMISSION_DENIED,"insufficient role")
    return c
def _j(v):
    if isinstance(v,Decimal): return str(v)
    if hasattr(v,"isoformat"): return v.isoformat()
    if isinstance(v,dict): return {k:_j(x) for k,x in v.items()}
    if isinstance(v,list): return [_j(x) for x in v]
    return v
def db(request): return request.app.state.settings.database_url.replace("postgresql+psycopg://","postgresql://",1)
def q(request,sql,args=()):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(db(request),row_factory=dict_row) as c: return c.execute(sql,args).fetchall()

class FiscalIn(BaseModel):
    name:str=Field(min_length=1,max_length=100); starts_on:date; ends_on:date
class PartyIn(BaseModel):
    name:str=Field(min_length=1,max_length=200); email:str|None=None; phone:str|None=None
class ProductIn(BaseModel):
    name:str=Field(min_length=1,max_length=200); sku:str|None=None; unit:str="عدد"; purchase_price:Decimal=Field(default=0,ge=0); sale_price:Decimal=Field(default=0,ge=0); track_inventory:bool=True
class WarehouseIn(BaseModel): name:str=Field(min_length=1,max_length=200)
class StockIn(BaseModel):
    warehouse_id:int; product_id:int; quantity:Decimal; movement_type:str; reference:str|None=None; movement_date:date
class CashIn(BaseModel):
    name:str=Field(min_length=1,max_length=200); kind:str; account_number:str|None=None; opening_balance:Decimal=0
class CashTxIn(BaseModel):
    cash_account_id:int; amount:Decimal=Field(gt=0); direction:str; description:str=""; reference:str|None=None; transaction_date:date
class CheckIn(BaseModel):
    party_name:str=Field(min_length=1,max_length=200); amount:Decimal=Field(gt=0); due_date:date; direction:str; bank_name:str|None=None; check_number:str|None=None; notes:str|None=None

@router.post("/{organization_id}/fiscal-years",status_code=201)
def create_fiscal_year(organization_id:int,p:FiscalIn,request:Request,c:Caller=Depends(write_caller)):
    if p.ends_on<p.starts_on: raise ApiError(ErrorCode.VALIDATION_ERROR,"fiscal year dates are invalid")
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        r=cn.execute("INSERT INTO fiscal_years(organization_id,name,starts_on,ends_on) VALUES(%s,%s,%s,%s) RETURNING *",(organization_id,p.name,p.starts_on,p.ends_on)).fetchone()
    return _j(dict(r))
@router.get("/{organization_id}/fiscal-years")
def fiscal_years(organization_id:int,request:Request,c:Caller=Depends(caller)): return {"items":_j(q(request,"SELECT * FROM fiscal_years WHERE organization_id=%s ORDER BY starts_on",(organization_id,)))}
@router.post("/{organization_id}/fiscal-years/{year_id}/close")
def close_year(organization_id:int,year_id:int,request:Request,c:Caller=Depends(write_caller)):
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        r=cn.execute("UPDATE fiscal_years SET status='closed' WHERE id=%s AND organization_id=%s AND status='open' RETURNING *",(year_id,organization_id)).fetchone()
    if not r: raise ApiError(ErrorCode.NOT_FOUND,"fiscal year not found or already closed")
    return _j(dict(r))

@router.post("/{organization_id}/suppliers",status_code=201)
def supplier(organization_id:int,p:PartyIn,request:Request,c:Caller=Depends(write_caller)):
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        return _j(dict(cn.execute("INSERT INTO suppliers(organization_id,name,email,phone) VALUES(%s,%s,%s,%s) RETURNING *",(organization_id,p.name,p.email,p.phone)).fetchone()))
@router.get("/{organization_id}/suppliers")
def suppliers(organization_id:int,request:Request,c:Caller=Depends(caller)): return {"items":_j(q(request,"SELECT * FROM suppliers WHERE organization_id=%s ORDER BY id",(organization_id,)))}

@router.post("/{organization_id}/products",status_code=201)
def product(organization_id:int,p:ProductIn,request:Request,c:Caller=Depends(write_caller)):
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        return _j(dict(cn.execute("INSERT INTO products(organization_id,name,sku,unit,purchase_price,sale_price,track_inventory) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",(organization_id,p.name,p.sku,p.unit,p.purchase_price,p.sale_price,p.track_inventory)).fetchone()))
@router.get("/{organization_id}/products")
def products(organization_id:int,request:Request,c:Caller=Depends(caller)): return {"items":_j(q(request,"SELECT * FROM products WHERE organization_id=%s ORDER BY name,id",(organization_id,)))}

@router.post("/{organization_id}/warehouses",status_code=201)
def warehouse(organization_id:int,p:WarehouseIn,request:Request,c:Caller=Depends(write_caller)):
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        return _j(dict(cn.execute("INSERT INTO warehouses(organization_id,name) VALUES(%s,%s) RETURNING *",(organization_id,p.name)).fetchone()))
@router.get("/{organization_id}/warehouses")
def warehouses(organization_id:int,request:Request,c:Caller=Depends(caller)): return {"items":_j(q(request,"SELECT * FROM warehouses WHERE organization_id=%s ORDER BY name",(organization_id,)))}

@router.post("/{organization_id}/stock-movements",status_code=201)
def stock(organization_id:int,p:StockIn,request:Request,c:Caller=Depends(write_caller)):
    if p.movement_type not in {"receipt","issue","transfer_in","transfer_out","adjustment"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid movement type")
    if p.quantity==0: raise ApiError(ErrorCode.VALIDATION_ERROR,"quantity cannot be zero")
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        ok=cn.execute("SELECT 1 FROM warehouses w JOIN products p ON p.organization_id=w.organization_id WHERE w.id=%s AND p.id=%s AND w.organization_id=%s",(p.warehouse_id,p.product_id,organization_id)).fetchone()
        if not ok: raise ApiError(ErrorCode.NOT_FOUND,"warehouse or product not found")
        r=cn.execute("INSERT INTO stock_movements(organization_id,warehouse_id,product_id,quantity,movement_type,reference,movement_date) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",(organization_id,p.warehouse_id,p.product_id,p.quantity,p.movement_type,p.reference,p.movement_date)).fetchone()
    return _j(dict(r))
@router.get("/{organization_id}/stock")
def stock_report(organization_id:int,request:Request,c:Caller=Depends(caller)):
    return {"items":_j(q(request,"SELECT product_id,warehouse_id,SUM(quantity) AS quantity FROM stock_movements WHERE organization_id=%s GROUP BY product_id,warehouse_id ORDER BY product_id,warehouse_id",(organization_id,)))}

@router.post("/{organization_id}/cash-accounts",status_code=201)
def cash_account(organization_id:int,p:CashIn,request:Request,c:Caller=Depends(write_caller)):
    if p.kind not in {"cash","bank"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid cash account kind")
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        r=cn.execute("INSERT INTO cash_accounts(organization_id,name,kind,account_number,opening_balance) VALUES(%s,%s,%s,%s,%s) RETURNING *",(organization_id,p.name,p.kind,p.account_number,p.opening_balance)).fetchone()
    return _j(dict(r))
@router.get("/{organization_id}/cash-accounts")
def cash_accounts(organization_id:int,request:Request,c:Caller=Depends(caller)): return {"items":_j(q(request,"SELECT * FROM cash_accounts WHERE organization_id=%s ORDER BY name",(organization_id,)))}
@router.post("/{organization_id}/cash-transactions",status_code=201)
def cash_tx(organization_id:int,p:CashTxIn,request:Request,c:Caller=Depends(write_caller)):
    if p.direction not in {"in","out"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid direction")
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        ok=cn.execute("SELECT 1 FROM cash_accounts WHERE id=%s AND organization_id=%s",(p.cash_account_id,organization_id)).fetchone()
        if not ok: raise ApiError(ErrorCode.NOT_FOUND,"cash account not found")
        r=cn.execute("INSERT INTO cash_transactions(organization_id,cash_account_id,amount,direction,description,reference,transaction_date) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",(organization_id,p.cash_account_id,p.amount,p.direction,p.description,p.reference,p.transaction_date)).fetchone()
    return _j(dict(r))
@router.get("/{organization_id}/cash-transactions")
def cash_transactions(organization_id:int,request:Request,c:Caller=Depends(caller)): return {"items":_j(q(request,"SELECT * FROM cash_transactions WHERE organization_id=%s ORDER BY transaction_date,id",(organization_id,)))}

@router.post("/{organization_id}/checks",status_code=201)
def create_check(organization_id:int,p:CheckIn,request:Request,c:Caller=Depends(write_caller)):
    if p.direction not in {"received","issued"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid check direction")
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        r=cn.execute("INSERT INTO checks(organization_id,party_name,amount,due_date,direction,bank_name,check_number,notes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",(organization_id,p.party_name,p.amount,p.due_date,p.direction,p.bank_name,p.check_number,p.notes)).fetchone()
    return _j(dict(r))
@router.get("/{organization_id}/checks")
def checks(organization_id:int,request:Request,c:Caller=Depends(caller)): return {"items":_j(q(request,"SELECT * FROM checks WHERE organization_id=%s ORDER BY due_date,id",(organization_id,)))}
@router.post("/{organization_id}/checks/{check_id}/status")
def check_status(organization_id:int,check_id:int,status:str,request:Request,c:Caller=Depends(write_caller)):
    if status not in {"pending","deposited","cleared","bounced","cancelled"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid check status")
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        r=cn.execute("UPDATE checks SET status=%s WHERE id=%s AND organization_id=%s RETURNING *",(status,check_id,organization_id)).fetchone()
    if not r: raise ApiError(ErrorCode.NOT_FOUND,"check not found")
    return _j(dict(r))
