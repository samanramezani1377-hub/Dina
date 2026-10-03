from __future__ import annotations
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
import psycopg
from psycopg.rows import dict_row
from .auth import token_user_id
from .errors import ApiError, ErrorCode
from .identity import Caller, resolve_caller
from .permissions import has_role
from .models import JournalLine
from .accounting import validate_journal

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
def connect(request): return psycopg.connect(db(request), row_factory=dict_row)
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
    warehouse_id:int; product_id:int; quantity:Decimal=Field(gt=0); movement_type:str; reference:str|None=None; movement_date:date
class StockTransferIn(BaseModel):
    source_warehouse_id:int; target_warehouse_id:int; product_id:int; quantity:Decimal=Field(gt=0); reference:str|None=None; movement_date:date
class CashIn(BaseModel):
    name:str=Field(min_length=1,max_length=200); kind:str; account_number:str|None=None; opening_balance:Decimal=0
    account_id:int|None=None
class CashTxIn(BaseModel):
    cash_account_id:int; amount:Decimal=Field(gt=0); direction:str; description:str=""; reference:str|None=None; transaction_date:date
    counter_account_id:int|None=None
class CheckIn(BaseModel):
    party_name:str=Field(min_length=1,max_length=200); amount:Decimal=Field(gt=0); due_date:date; direction:str; bank_name:str|None=None; check_number:str|None=None; notes:str|None=None

@router.post("/{organization_id}/fiscal-years",status_code=201)
def create_fiscal_year(organization_id:int,p:FiscalIn,request:Request,c:Caller=Depends(write_caller)):
    if p.ends_on<p.starts_on: raise ApiError(ErrorCode.VALIDATION_ERROR,"fiscal year dates are invalid")
    with connect(request) as cn:
        overlap=cn.execute("SELECT 1 FROM fiscal_years WHERE organization_id=%s AND starts_on<=%s AND ends_on>=%s LIMIT 1",(organization_id,p.ends_on,p.starts_on)).fetchone()
        if overlap: raise ApiError(ErrorCode.VALIDATION_ERROR,"fiscal year overlaps an existing fiscal year")
        r=cn.execute("INSERT INTO fiscal_years(organization_id,name,starts_on,ends_on) VALUES(%s,%s,%s,%s) RETURNING *",(organization_id,p.name,p.starts_on,p.ends_on)).fetchone()
    return _j(dict(r))
@router.get("/{organization_id}/fiscal-years")
def fiscal_years(organization_id:int,request:Request,c:Caller=Depends(caller)): return {"items":_j(q(request,"SELECT * FROM fiscal_years WHERE organization_id=%s ORDER BY starts_on",(organization_id,)))}
@router.post("/{organization_id}/fiscal-years/{year_id}/close")
def close_year(organization_id:int,year_id:int,request:Request,c:Caller=Depends(write_caller)):
    with connect(request) as cn:
        year=cn.execute("SELECT * FROM fiscal_years WHERE id=%s AND organization_id=%s FOR UPDATE",(year_id,organization_id)).fetchone()
        if not year: raise ApiError(ErrorCode.NOT_FOUND,"fiscal year not found")
        if year["status"]!="open": raise ApiError(ErrorCode.VALIDATION_ERROR,"fiscal year is already closed")
        pending=cn.execute("SELECT 1 FROM sales WHERE organization_id=%s AND issue_date BETWEEN %s AND %s AND status='draft' UNION ALL SELECT 1 FROM purchases WHERE organization_id=%s AND issue_date BETWEEN %s AND %s AND status='draft' LIMIT 1",(organization_id,year["starts_on"],year["ends_on"],organization_id,year["starts_on"],year["ends_on"])).fetchone()
        if pending: raise ApiError(ErrorCode.VALIDATION_ERROR,"draft sales or purchases exist in this fiscal year")
        r=cn.execute("UPDATE fiscal_years SET status='closed' WHERE id=%s AND organization_id=%s RETURNING *",(year_id,organization_id)).fetchone()
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
    with connect(request) as cn:
        ok=cn.execute("SELECT 1 FROM warehouses w JOIN products p ON p.organization_id=w.organization_id WHERE w.id=%s AND p.id=%s AND w.organization_id=%s",(p.warehouse_id,p.product_id,organization_id)).fetchone()
        if not ok: raise ApiError(ErrorCode.NOT_FOUND,"warehouse or product not found")
        cn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"stock:{organization_id}:{p.warehouse_id}:{p.product_id}",))
        signed=p.quantity if p.movement_type in {"receipt","transfer_in","adjustment"} else -p.quantity
        if p.movement_type in {"issue","transfer_out"}:
            balance=cn.execute("SELECT COALESCE(SUM(quantity),0) AS quantity FROM stock_movements WHERE organization_id=%s AND warehouse_id=%s AND product_id=%s",(organization_id,p.warehouse_id,p.product_id)).fetchone()["quantity"]
            if Decimal(balance)<p.quantity: raise ApiError(ErrorCode.VALIDATION_ERROR,"insufficient stock")
        r=cn.execute("INSERT INTO stock_movements(organization_id,warehouse_id,product_id,quantity,movement_type,reference,movement_date,unit_cost) VALUES(%s,%s,%s,%s,%s,%s,%s,COALESCE((SELECT purchase_price FROM products WHERE id=%s),0)) RETURNING *",(organization_id,p.warehouse_id,p.product_id,signed,p.movement_type,p.reference,p.movement_date,p.product_id)).fetchone()
    return _j(dict(r))

@router.post("/{organization_id}/stock-transfers",status_code=201)
def stock_transfer(organization_id:int,p:StockTransferIn,request:Request,c:Caller=Depends(write_caller)):
    if p.source_warehouse_id==p.target_warehouse_id: raise ApiError(ErrorCode.VALIDATION_ERROR,"source and target warehouses must differ")
    with connect(request) as cn:
        ok=cn.execute("SELECT EXISTS(SELECT 1 FROM warehouses WHERE id=%s AND organization_id=%s) AS source_ok, EXISTS(SELECT 1 FROM warehouses WHERE id=%s AND organization_id=%s) AS target_ok, EXISTS(SELECT 1 FROM products WHERE id=%s AND organization_id=%s) AS product_ok",(p.source_warehouse_id,organization_id,p.target_warehouse_id,organization_id,p.product_id,organization_id)).fetchone()
        if not ok["source_ok"] or not ok["target_ok"] or not ok["product_ok"]: raise ApiError(ErrorCode.NOT_FOUND,"warehouse or product not found")
        cn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"stock:{organization_id}:{p.product_id}",))
        balance=cn.execute("SELECT COALESCE(SUM(quantity),0) AS quantity FROM stock_movements WHERE organization_id=%s AND warehouse_id=%s AND product_id=%s",(organization_id,p.source_warehouse_id,p.product_id)).fetchone()["quantity"]
        if Decimal(balance)<p.quantity: raise ApiError(ErrorCode.VALIDATION_ERROR,"insufficient stock")
        avg=cn.execute("SELECT COALESCE(SUM(quantity*unit_cost) FILTER (WHERE quantity>0),0)/NULLIF(SUM(quantity) FILTER (WHERE quantity>0),0) AS cost FROM stock_movements WHERE organization_id=%s AND warehouse_id=%s AND product_id=%s",(organization_id,p.source_warehouse_id,p.product_id)).fetchone()["cost"]
        out_row=cn.execute("INSERT INTO stock_movements(organization_id,warehouse_id,product_id,quantity,movement_type,reference,movement_date,unit_cost) VALUES(%s,%s,%s,%s,'transfer_out',%s,%s,%s) RETURNING id",(organization_id,p.source_warehouse_id,p.product_id,-p.quantity,p.reference,p.movement_date,avg)).fetchone()
        in_row=cn.execute("INSERT INTO stock_movements(organization_id,warehouse_id,product_id,quantity,movement_type,reference,movement_date,unit_cost) VALUES(%s,%s,%s,%s,'transfer_in',%s,%s,%s) RETURNING id",(organization_id,p.target_warehouse_id,p.product_id,p.quantity,p.reference,p.movement_date,avg)).fetchone()
    return {"source_movement_id":out_row["id"],"target_movement_id":in_row["id"],"quantity":str(p.quantity),"unit_cost":str(avg)}
@router.get("/{organization_id}/stock")
def stock_report(organization_id:int,request:Request,c:Caller=Depends(caller)):
    return {"items":_j(q(request,"SELECT product_id,warehouse_id,SUM(quantity) AS quantity FROM stock_movements WHERE organization_id=%s GROUP BY product_id,warehouse_id ORDER BY product_id,warehouse_id",(organization_id,)))}

@router.post("/{organization_id}/cash-accounts",status_code=201)
def cash_account(organization_id:int,p:CashIn,request:Request,c:Caller=Depends(write_caller)):
    if p.kind not in {"cash","bank"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid cash account kind")
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        r=cn.execute("INSERT INTO cash_accounts(organization_id,name,kind,account_number,opening_balance,account_id) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",(organization_id,p.name,p.kind,p.account_number,p.opening_balance,p.account_id)).fetchone()
    return _j(dict(r))
@router.get("/{organization_id}/cash-accounts")
def cash_accounts(organization_id:int,request:Request,c:Caller=Depends(caller)): return {"items":_j(q(request,"SELECT * FROM cash_accounts WHERE organization_id=%s ORDER BY name",(organization_id,)))}
@router.post("/{organization_id}/cash-transactions",status_code=201)
def cash_tx(organization_id:int,p:CashTxIn,request:Request,c:Caller=Depends(write_caller)):
    if p.direction not in {"in","out"}: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid direction")
    with __import__("psycopg").connect(db(request),row_factory=__import__("psycopg").rows.dict_row) as cn:
        ok=cn.execute("SELECT 1 FROM cash_accounts WHERE id=%s AND organization_id=%s",(p.cash_account_id,organization_id)).fetchone()
        if not ok: raise ApiError(ErrorCode.NOT_FOUND,"cash account not found")
        r=cn.execute("INSERT INTO cash_transactions(organization_id,cash_account_id,amount,direction,description,reference,transaction_date,counter_account_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",(organization_id,p.cash_account_id,p.amount,p.direction,p.description,p.reference,p.transaction_date,p.counter_account_id)).fetchone()
    return _j(dict(r))
@router.get("/{organization_id}/cash-accounts/{cash_account_id}/balance")
def cash_balance(organization_id:int,cash_account_id:int,request:Request,c:Caller=Depends(caller)):
    with connect(request) as cn:
        row=cn.execute("""SELECT ca.id,ca.name,ca.kind,ca.opening_balance,
                         ca.opening_balance + COALESCE(SUM(CASE WHEN ct.direction='in' THEN ct.amount ELSE -ct.amount END),0) AS balance
                         FROM cash_accounts ca LEFT JOIN cash_transactions ct
                         ON ct.cash_account_id=ca.id AND ct.organization_id=ca.organization_id
                         WHERE ca.id=%s AND ca.organization_id=%s
                         GROUP BY ca.id,ca.name,ca.kind,ca.opening_balance""",(cash_account_id,organization_id)).fetchone()
    if not row: raise ApiError(ErrorCode.NOT_FOUND,"cash account not found")
    return _j(dict(row))

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
    allowed={"pending":{"deposited","bounced","cancelled"},"deposited":{"cleared","bounced","cancelled"},"cleared":set(),"bounced":set(),"cancelled":set()}
    if status not in allowed: raise ApiError(ErrorCode.VALIDATION_ERROR,"invalid check status")
    with connect(request) as cn:
        r=cn.execute("SELECT * FROM checks WHERE id=%s AND organization_id=%s FOR UPDATE",(check_id,organization_id)).fetchone()
        if not r: raise ApiError(ErrorCode.NOT_FOUND,"check not found")
        if status==r["status"]: return _j(dict(r))
        if status not in allowed.get(r["status"],set()): raise ApiError(ErrorCode.VALIDATION_ERROR,f"invalid check transition: {r['status']} -> {status}")
        r=cn.execute("UPDATE checks SET status=%s WHERE id=%s AND organization_id=%s RETURNING *",(status,check_id,organization_id)).fetchone()
    return _j(dict(r))

class DocumentLineIn(BaseModel):
    product_id:int|None=None; description:str=Field(min_length=1,max_length=500)
    quantity:Decimal=Field(gt=0); unit_price:Decimal=Field(ge=0)
    discount:Decimal=Field(default=0,ge=0); tax:Decimal=Field(default=0,ge=0)
class SalesDocumentIn(BaseModel):
    customer_id:int; invoice_no:str=Field(min_length=1,max_length=100); issue_date:date
    due_date:date|None=None; warehouse_id:int|None=None; lines:list[DocumentLineIn]=Field(min_length=1)
class PurchaseDocumentIn(BaseModel):
    supplier_id:int; invoice_no:str=Field(min_length=1,max_length=100); issue_date:date
    due_date:date|None=None; warehouse_id:int|None=None; lines:list[DocumentLineIn]=Field(min_length=1)

def _doc_totals(lines):
    subtotal=sum((x.quantity*x.unit_price for x in lines),Decimal("0"))
    discount=sum((x.discount for x in lines),Decimal("0"))
    tax=sum((x.tax for x in lines),Decimal("0"))
    return subtotal,discount,tax,subtotal-discount+tax

@router.post("/{organization_id}/sales",status_code=201)
def create_sale(organization_id:int,p:SalesDocumentIn,request:Request,c:Caller=Depends(write_caller)):
    subtotal,discount,tax,total=_doc_totals(p.lines)
    with connect(request) as cn:
        customer=cn.execute("SELECT 1 FROM customers WHERE id=%s AND organization_id=%s",(p.customer_id,organization_id)).fetchone()
        if not customer: raise ApiError(ErrorCode.NOT_FOUND,"customer not found")
        r=cn.execute("INSERT INTO sales(organization_id,customer_id,invoice_no,issue_date,due_date,warehouse_id,subtotal,discount,tax,total) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",(organization_id,p.customer_id,p.invoice_no,p.issue_date,p.due_date,p.warehouse_id,subtotal,discount,tax,total)).fetchone()
        for x in p.lines:
            if x.product_id:
                ok=cn.execute("SELECT 1 FROM products WHERE id=%s AND organization_id=%s",(x.product_id,organization_id)).fetchone()
                if not ok: raise ApiError(ErrorCode.NOT_FOUND,"product not found")
            cn.execute("INSERT INTO sale_lines(sale_id,product_id,description,quantity,unit_price,discount,tax) VALUES(%s,%s,%s,%s,%s,%s,%s)",(r["id"],x.product_id,x.description,x.quantity,x.unit_price,x.discount,x.tax))
    return _j(dict(r))
@router.get("/{organization_id}/sales")
def sales(organization_id:int,request:Request,c:Caller=Depends(caller)):
    return {"items":_j(q(request,"SELECT * FROM sales WHERE organization_id=%s ORDER BY issue_date DESC,id DESC",(organization_id,)))}

@router.post("/{organization_id}/purchases",status_code=201)
def create_purchase(organization_id:int,p:PurchaseDocumentIn,request:Request,c:Caller=Depends(write_caller)):
    subtotal,discount,tax,total=_doc_totals(p.lines)
    with connect(request) as cn:
        supplier=cn.execute("SELECT 1 FROM suppliers WHERE id=%s AND organization_id=%s",(p.supplier_id,organization_id)).fetchone()
        if not supplier: raise ApiError(ErrorCode.NOT_FOUND,"supplier not found")
        r=cn.execute("INSERT INTO purchases(organization_id,supplier_id,invoice_no,issue_date,due_date,warehouse_id,subtotal,discount,tax,total) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",(organization_id,p.supplier_id,p.invoice_no,p.issue_date,p.due_date,p.warehouse_id,subtotal,discount,tax,total)).fetchone()
        for x in p.lines:
            if x.product_id:
                ok=cn.execute("SELECT 1 FROM products WHERE id=%s AND organization_id=%s",(x.product_id,organization_id)).fetchone()
                if not ok: raise ApiError(ErrorCode.NOT_FOUND,"product not found")
            cn.execute("INSERT INTO purchase_lines(purchase_id,product_id,description,quantity,unit_price,discount,tax) VALUES(%s,%s,%s,%s,%s,%s,%s)",(r["id"],x.product_id,x.description,x.quantity,x.unit_price,x.discount,x.tax))
    return _j(dict(r))
@router.get("/{organization_id}/purchases")
def purchases(organization_id:int,request:Request,c:Caller=Depends(caller)):
    return {"items":_j(q(request,"SELECT * FROM purchases WHERE organization_id=%s ORDER BY issue_date DESC,id DESC",(organization_id,)))}


class DocumentPostIn(BaseModel):
    receivable_or_payable_account_id:int
    revenue_or_inventory_account_id:int
    tax_account_id:int|None=None
    discount_account_id:int|None=None
    inventory_account_id:int|None=None
    cogs_account_id:int|None=None
    warehouse_id:int|None=None

def _open_fiscal_year(cn,organization_id,entry_date):
    row=cn.execute("SELECT id FROM fiscal_years WHERE organization_id=%s AND status='open' AND starts_on<=%s AND ends_on>=%s FOR UPDATE",(organization_id,entry_date,entry_date)).fetchone()
    if not row: raise ApiError(ErrorCode.VALIDATION_ERROR,"no open fiscal year covers this document date")

def _add_entry(cn,organization_id,document_no,description,entry_date,lines):
    validate_journal(lines)
    for line in lines:
        if not cn.execute("SELECT 1 FROM accounts WHERE id=%s AND organization_id=%s",(line.account_id,organization_id)).fetchone(): raise ApiError(ErrorCode.NOT_FOUND,"account does not exist in this organization")
    try:
        row=cn.execute("INSERT INTO journal_entries(organization_id,document_no,description,status,entry_date,posted_at) VALUES(%s,%s,%s,'posted',%s,NOW()) RETURNING id",(organization_id,document_no,description,entry_date)).fetchone()
    except psycopg.errors.UniqueViolation:
        raise ApiError(ErrorCode.VALIDATION_ERROR,"document number already exists in this organization")
    for line in lines:
        cn.execute("INSERT INTO journal_lines(journal_entry_id,account_id,debit,credit) VALUES(%s,%s,%s,%s)",(row["id"],line.account_id,line.debit,line.credit))
    return row["id"]

def _average_cost(cn,organization_id,warehouse_id,product_id):
    row=cn.execute("SELECT COALESCE(SUM(quantity*unit_cost) FILTER (WHERE quantity>0),0)/NULLIF(SUM(quantity) FILTER (WHERE quantity>0),0) AS cost FROM stock_movements WHERE organization_id=%s AND warehouse_id=%s AND product_id=%s",(organization_id,warehouse_id,product_id)).fetchone()
    return Decimal(row["cost"] or 0)

def _post_document(request, organization_id, document_table, line_table, document_id, p, is_sale):
    with connect(request) as cn:
        doc=cn.execute(f"SELECT * FROM {document_table} WHERE id=%s AND organization_id=%s FOR UPDATE",(document_id,organization_id)).fetchone()
        if not doc: raise ApiError(ErrorCode.NOT_FOUND,"document not found")
        if doc["status"]!="draft": raise ApiError(ErrorCode.VALIDATION_ERROR,"document is not in draft status")
        _open_fiscal_year(cn,organization_id,doc["issue_date"])
        warehouse_id=p.warehouse_id or doc["warehouse_id"]
        item_rows=cn.execute(f"SELECT * FROM {line_table} WHERE {("sale_id" if is_sale else "purchase_id") }=%s ORDER BY id",(document_id,)).fetchall()
        if is_sale:
            lines=[JournalLine(p.receivable_or_payable_account_id,doc["total"],Decimal("0")),JournalLine(p.revenue_or_inventory_account_id,Decimal("0"),doc["subtotal"]-doc["discount"])]
        else:
            lines=[JournalLine(p.revenue_or_inventory_account_id,doc["subtotal"]-doc["discount"],Decimal("0")),JournalLine(p.receivable_or_payable_account_id,Decimal("0"),doc["total"])]
        if doc["tax"]>0:
            if not p.tax_account_id: raise ApiError(ErrorCode.VALIDATION_ERROR,"tax account is required when document has tax")
            lines.append(JournalLine(p.tax_account_id,Decimal("0"),doc["tax"]) if is_sale else JournalLine(p.tax_account_id,doc["tax"],Decimal("0")))
        if doc["discount"]>0 and p.discount_account_id:
            lines.append(JournalLine(p.discount_account_id,doc["discount"],Decimal("0")) if is_sale else JournalLine(p.discount_account_id,Decimal("0"),doc["discount"]))
        inventory_total=Decimal("0")
        tracked=[x for x in item_rows if x["product_id"]]
        if tracked and warehouse_id is None:
            raise ApiError(ErrorCode.VALIDATION_ERROR,"warehouse is required for product documents")
        if warehouse_id:
            if not cn.execute("SELECT 1 FROM warehouses WHERE id=%s AND organization_id=%s",(warehouse_id,organization_id)).fetchone(): raise ApiError(ErrorCode.NOT_FOUND,"warehouse not found")
        for x in item_rows:
            if not x["product_id"]: continue
            prod=cn.execute("SELECT * FROM products WHERE id=%s AND organization_id=%s FOR UPDATE",(x["product_id"],organization_id)).fetchone()
            if not prod: raise ApiError(ErrorCode.NOT_FOUND,"product not found")
            if not prod["track_inventory"]: continue
            if is_sale:
                if p.cogs_account_id is None or p.inventory_account_id is None: raise ApiError(ErrorCode.VALIDATION_ERROR,"cogs and inventory accounts are required for inventory sales")
                cn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(f"stock:{organization_id}:{warehouse_id}:{x['product_id']}",))
                bal=cn.execute("SELECT COALESCE(SUM(quantity),0) AS q FROM stock_movements WHERE organization_id=%s AND warehouse_id=%s AND product_id=%s",(organization_id,warehouse_id,x["product_id"])).fetchone()["q"]
                if Decimal(bal)<Decimal(x["quantity"]): raise ApiError(ErrorCode.VALIDATION_ERROR,"insufficient stock for sale")
                unit_cost=_average_cost(cn,organization_id,warehouse_id,x["product_id"])
                cost=unit_cost*Decimal(x["quantity"])
                inventory_total+=cost
                cn.execute("INSERT INTO stock_movements(organization_id,warehouse_id,product_id,quantity,movement_type,reference,movement_date,unit_cost) VALUES(%s,%s,%s,%s,'issue',%s,%s,%s)",(organization_id,warehouse_id,x["product_id"],-x["quantity"],doc["invoice_no"],doc["issue_date"],unit_cost))
            else:
                cost=(Decimal(x["quantity"])*Decimal(x["unit_price"])-Decimal(x["discount"]))/Decimal(x["quantity"])
                cn.execute("INSERT INTO stock_movements(organization_id,warehouse_id,product_id,quantity,movement_type,reference,movement_date,unit_cost) VALUES(%s,%s,%s,%s,'receipt',%s,%s,%s)",(organization_id,warehouse_id,x["product_id"],x["quantity"],doc["invoice_no"],doc["issue_date"],cost))
        if inventory_total:
            lines.append(JournalLine(p.cogs_account_id,inventory_total,Decimal("0")))
            lines.append(JournalLine(p.inventory_account_id,Decimal("0"),inventory_total))
        entry_id=_add_entry(cn,organization_id,doc["invoice_no"],("Sale " if is_sale else "Purchase ")+doc["invoice_no"],doc["issue_date"],lines)
        cn.execute(f"UPDATE {document_table} SET status='posted',journal_entry_id=%s WHERE id=%s AND organization_id=%s",(entry_id,document_id,organization_id))
    return _j({"document_id":document_id,"status":"posted","journal_entry_id":entry_id})
@router.post("/{organization_id}/sales/{sale_id}/post")
def post_sale(organization_id:int,sale_id:int,p:DocumentPostIn,request:Request,c:Caller=Depends(write_caller)):
    return _post_document(request,organization_id,"sales","sale_lines",sale_id,p,True)

@router.post("/{organization_id}/purchases/{purchase_id}/post")
def post_purchase(organization_id:int,purchase_id:int,p:DocumentPostIn,request:Request,c:Caller=Depends(write_caller)):
    return _post_document(request,organization_id,"purchases","purchase_lines",purchase_id,p,False)
