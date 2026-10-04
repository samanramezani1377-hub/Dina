from __future__ import annotations
import csv, io
from datetime import date
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import StreamingResponse
from .financial_reports_api import rows
from .identity import Caller
from .ledger_api import require_accounting_caller
router=APIRouter(prefix="/api/v1/organizations",tags=["exports"])
def _csv(filename,headers,records):
    buf=io.StringIO(); writer=csv.writer(buf); writer.writerow(headers)
    for r in records: writer.writerow([r.get(h,"") for h in headers])
    return StreamingResponse(iter([buf.getvalue().encode("utf-8-sig")]),media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":f'attachment; filename="{filename}"'})
@router.get("/{organization_id}/exports/trial-balance.csv")
def trial_balance_csv(organization_id:int,request:Request,as_of:date|None=Query(None),caller:Caller=Depends(require_accounting_caller)):
    d=as_of or date.max
    r=[dict(x) for x in rows(request,"""SELECT a.code,a.name,a.account_type,COALESCE(SUM(jl.debit),0) debit,
        COALESCE(SUM(jl.credit),0) credit FROM accounts a LEFT JOIN journal_lines jl ON jl.account_id=a.id
        LEFT JOIN journal_entries je ON je.id=jl.journal_entry_id AND je.organization_id=a.organization_id
        AND je.status='posted' AND je.entry_date<=%s WHERE a.organization_id=%s GROUP BY a.id ORDER BY a.code""",(d,organization_id))]
    return _csv("dina-trial-balance.csv",["code","name","account_type","debit","credit"],r)
@router.get("/{organization_id}/exports/ledger.csv")
def ledger_csv(organization_id:int,request:Request,date_from:date|None=Query(None),date_to:date|None=Query(None),caller:Caller=Depends(require_accounting_caller)):
    params=[organization_id]; where="je.organization_id=%s AND je.status IN ('posted','reversed')"
    if date_from: where+=" AND je.entry_date>=%s"; params.append(date_from)
    if date_to: where+=" AND je.entry_date<=%s"; params.append(date_to)
    r=[dict(x) for x in rows(request,f"""SELECT a.code,a.name,je.document_no,je.entry_date,je.description,jl.debit,jl.credit
        FROM journal_entries je JOIN journal_lines jl ON jl.journal_entry_id=je.id JOIN accounts a ON a.id=jl.account_id
        WHERE {where} ORDER BY je.entry_date,je.id,jl.id""",params)]
    return _csv("dina-ledger.csv",["code","name","document_no","entry_date","description","debit","credit"],r)
@router.get("/{organization_id}/exports/sales.csv")
def sales_csv(organization_id:int,request:Request,date_from:date|None=Query(None),date_to:date|None=Query(None),caller:Caller=Depends(require_accounting_caller)):
    params=[organization_id]; where="organization_id=%s AND status='posted'"
    if date_from: where+=" AND issue_date>=%s"; params.append(date_from)
    if date_to: where+=" AND issue_date<=%s"; params.append(date_to)
    r=[dict(x) for x in rows(request,f"SELECT invoice_no,issue_date,subtotal,discount,tax,total,status,journal_entry_id FROM sales WHERE {where} ORDER BY issue_date,id",params)]
    return _csv("dina-sales.csv",["invoice_no","issue_date","subtotal","discount","tax","total","status","journal_entry_id"],r)
@router.get("/{organization_id}/exports/purchases.csv")
def purchases_csv(organization_id:int,request:Request,date_from:date|None=Query(None),date_to:date|None=Query(None),caller:Caller=Depends(require_accounting_caller)):
    params=[organization_id]; where="organization_id=%s AND status='posted'"
    if date_from: where+=" AND issue_date>=%s"; params.append(date_from)
    if date_to: where+=" AND issue_date<=%s"; params.append(date_to)
    r=[dict(x) for x in rows(request,f"SELECT invoice_no,issue_date,subtotal,discount,tax,total,status,journal_entry_id FROM purchases WHERE {where} ORDER BY issue_date,id",params)]
    return _csv("dina-purchases.csv",["invoice_no","issue_date","subtotal","discount","tax","total","status","journal_entry_id"],r)
@router.get("/{organization_id}/exports/inventory.csv")
def inventory_csv(organization_id:int,request:Request,warehouse_id:int|None=Query(None),product_id:int|None=Query(None),caller:Caller=Depends(require_accounting_caller)):
    params=[organization_id]; where="sm.organization_id=%s"
    if warehouse_id is not None: where+=" AND sm.warehouse_id=%s"; params.append(warehouse_id)
    if product_id is not None: where+=" AND sm.product_id=%s"; params.append(product_id)
    r=[dict(x) for x in rows(request,"""SELECT w.name warehouse,p.name product,COALESCE(SUM(sm.quantity),0) quantity,
        COALESCE(SUM(CASE WHEN sm.quantity>0 THEN sm.quantity*sm.unit_cost ELSE 0 END),0) received_value
        FROM stock_movements sm JOIN products p ON p.id=sm.product_id JOIN warehouses w ON w.id=sm.warehouse_id
        WHERE """+where+" GROUP BY w.name,p.name ORDER BY w.name,p.name",params)]
    return _csv("dina-inventory.csv",["warehouse","product","quantity","received_value"],r)
