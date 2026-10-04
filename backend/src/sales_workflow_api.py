from __future__ import annotations
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from .auth import token_user_id
from .errors import ApiError, ErrorCode
from .identity import Caller, resolve_caller
from .permissions import has_role
from .business_modules_api import connect, _j

router = APIRouter(prefix="/api/v1/organizations", tags=["sales-workflow"])

def _read_caller(organization_id:int, request:Request, user_id:int=Depends(token_user_id))->Caller:
    c=resolve_caller(user_id,organization_id,request.app.state.memberships)
    if not has_role(c.role,"viewer"): raise ApiError(ErrorCode.PERMISSION_DENIED,"insufficient role")
    return c
def _write_caller(organization_id:int, request:Request, user_id:int=Depends(token_user_id))->Caller:
    c=resolve_caller(user_id,organization_id,request.app.state.memberships)
    if not has_role(c.role,"accountant"): raise ApiError(ErrorCode.PERMISSION_DENIED,"insufficient role")
    return c

class PriceListIn(BaseModel):
    name:str=Field(min_length=1,max_length=120)
class ProductPriceIn(BaseModel):
    product_id:int
    price:Decimal=Field(ge=0)
class CreditIn(BaseModel):
    credit_limit:Decimal=Field(ge=0)
    credit_invoice_limit:int=Field(ge=0)
class InstallmentIn(BaseModel):
    due_date:date
    amount:Decimal=Field(gt=0)
class InstallmentPaymentIn(BaseModel):
    amount:Decimal=Field(gt=0)

@router.post("/{organization_id}/price-lists",status_code=201)
def create_price_list(organization_id:int,p:PriceListIn,request:Request,c:Caller=Depends(_write_caller)):
    with connect(request) as cn:
        if cn.execute("SELECT 1 FROM price_lists WHERE organization_id=%s AND name=%s",(organization_id,p.name)).fetchone():
            raise ApiError(ErrorCode.VALIDATION_ERROR,"price list name already exists")
        row=cn.execute("INSERT INTO price_lists(organization_id,name) VALUES(%s,%s) RETURNING *",(organization_id,p.name)).fetchone()
    return _j(dict(row))

@router.get("/{organization_id}/price-lists")
def list_price_lists(organization_id:int,request:Request,c:Caller=Depends(_read_caller)):
    with connect(request) as cn:
        rows=cn.execute("SELECT * FROM price_lists WHERE organization_id=%s ORDER BY name",(organization_id,)).fetchall()
    return {"items":_j(rows)}

@router.put("/{organization_id}/price-lists/{price_list_id}/prices")
def set_product_price(organization_id:int,price_list_id:int,p:ProductPriceIn,request:Request,c:Caller=Depends(_write_caller)):
    with connect(request) as cn:
        if not cn.execute("SELECT 1 FROM price_lists WHERE id=%s AND organization_id=%s",(price_list_id,organization_id)).fetchone() or not cn.execute("SELECT 1 FROM products WHERE id=%s AND organization_id=%s",(p.product_id,organization_id)).fetchone():
            raise ApiError(ErrorCode.NOT_FOUND,"price list or product not found")
        row=cn.execute("""INSERT INTO product_prices(price_list_id,product_id,price) VALUES(%s,%s,%s)
        ON CONFLICT(price_list_id,product_id) DO UPDATE SET price=EXCLUDED.price RETURNING *""",(price_list_id,p.product_id,p.price)).fetchone()
    return _j(dict(row))

@router.get("/{organization_id}/price-lists/{price_list_id}/prices")
def list_product_prices(organization_id:int,price_list_id:int,request:Request,c:Caller=Depends(_read_caller)):
    with connect(request) as cn:
        rows=cn.execute("""SELECT pp.*,p.name AS product_name,p.sku FROM product_prices pp
        JOIN price_lists pl ON pl.id=pp.price_list_id JOIN products p ON p.id=pp.product_id
        WHERE pl.id=%s AND pl.organization_id=%s ORDER BY p.name""",(price_list_id,organization_id)).fetchall()
    return {"items":_j(rows)}

@router.put("/{organization_id}/customers/{customer_id}/credit")
def set_customer_credit(organization_id:int,customer_id:int,p:CreditIn,request:Request,c:Caller=Depends(_write_caller)):
    with connect(request) as cn:
        row=cn.execute("UPDATE customers SET credit_limit=%s,credit_invoice_limit=%s WHERE id=%s AND organization_id=%s RETURNING *",(p.credit_limit,p.credit_invoice_limit,customer_id,organization_id)).fetchone()
    if not row: raise ApiError(ErrorCode.NOT_FOUND,"customer not found")
    return _j(dict(row))

@router.get("/{organization_id}/customers/{customer_id}/credit")
def customer_credit(organization_id:int,customer_id:int,request:Request,c:Caller=Depends(_read_caller)):
    with connect(request) as cn:
        customer=cn.execute("SELECT id,name,credit_limit,credit_invoice_limit FROM customers WHERE id=%s AND organization_id=%s",(customer_id,organization_id)).fetchone()
        if not customer: raise ApiError(ErrorCode.NOT_FOUND,"customer not found")
        exposure=cn.execute("""SELECT COALESCE(SUM(total),0) AS amount,COUNT(*) AS invoice_count
        FROM sales WHERE organization_id=%s AND customer_id=%s AND status='posted' AND total > 0""",(organization_id,customer_id)).fetchone()
    return _j({"customer":dict(customer),"exposure":dict(exposure)})

@router.post("/{organization_id}/sales/{sale_id}/installments",status_code=201)
def create_installment(organization_id:int,sale_id:int,p:InstallmentIn,request:Request,c:Caller=Depends(_write_caller)):
    with connect(request) as cn:
        sale=cn.execute("SELECT total FROM sales WHERE id=%s AND organization_id=%s",(sale_id,organization_id)).fetchone()
        if not sale: raise ApiError(ErrorCode.NOT_FOUND,"sale not found")
        used=cn.execute("SELECT COALESCE(SUM(amount),0) AS amount FROM sales_installments WHERE sale_id=%s AND status<>'cancelled'",(sale_id,)).fetchone()
        if Decimal(used["amount"])+p.amount>Decimal(sale["total"]): raise ApiError(ErrorCode.VALIDATION_ERROR,"installments exceed invoice total")
        no=cn.execute("SELECT COALESCE(MAX(installment_no),0)+1 AS no FROM sales_installments WHERE sale_id=%s",(sale_id,)).fetchone()["no"]
        row=cn.execute("INSERT INTO sales_installments(organization_id,sale_id,installment_no,due_date,amount) VALUES(%s,%s,%s,%s,%s) RETURNING *",(organization_id,sale_id,no,p.due_date,p.amount)).fetchone()
    return _j(dict(row))

@router.get("/{organization_id}/sales/{sale_id}/installments")
def list_installments(organization_id:int,sale_id:int,request:Request,c:Caller=Depends(_read_caller)):
    with connect(request) as cn:
        rows=cn.execute("SELECT * FROM sales_installments WHERE organization_id=%s AND sale_id=%s ORDER BY installment_no",(organization_id,sale_id)).fetchall()
    return {"items":_j(rows)}

@router.post("/{organization_id}/sales-installments/{installment_id}/pay")
def pay_installment(organization_id:int,installment_id:int,p:InstallmentPaymentIn,request:Request,c:Caller=Depends(_write_caller)):
    with connect(request) as cn:
        row=cn.execute("SELECT * FROM sales_installments WHERE id=%s AND organization_id=%s FOR UPDATE",(installment_id,organization_id)).fetchone()
        if not row: raise ApiError(ErrorCode.NOT_FOUND,"installment not found")
        remaining=Decimal(row["amount"])-Decimal(row["paid_amount"])
        if p.amount>remaining: raise ApiError(ErrorCode.VALIDATION_ERROR,"payment exceeds remaining installment")
        paid=Decimal(row["paid_amount"])+p.amount
        status="paid" if paid==Decimal(row["amount"]) else "partial"
        row=cn.execute("UPDATE sales_installments SET paid_amount=%s,status=%s WHERE id=%s RETURNING *",(paid,status,installment_id)).fetchone()
    return _j(dict(row))
