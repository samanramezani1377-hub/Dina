from __future__ import annotations
from datetime import date
from fastapi import APIRouter, Depends, Request, Query
from .identity import Caller
from .ledger_api import require_accounting_caller
router=APIRouter(prefix="/api/v1/organizations",tags=["financial-reports"])
def rows(request,sql,args):
 import psycopg
 from psycopg.rows import dict_row
 with psycopg.connect(request.app.state.settings.database_url.replace("postgresql+psycopg://","postgresql://",1),row_factory=dict_row) as c:return c.execute(sql,args).fetchall()
@router.get("/{organization_id}/reports/profit-loss")
def profit_loss(organization_id:int,request:Request,as_of:date|None=Query(None),caller:Caller=Depends(require_accounting_caller)):
 d=as_of or date.max
 r=rows(request,"""SELECT a.id,a.code,a.name,a.account_type,COALESCE(SUM(jl.debit),0) debit,COALESCE(SUM(jl.credit),0) credit FROM accounts a LEFT JOIN journal_lines jl ON jl.account_id=a.id LEFT JOIN journal_entries je ON je.id=jl.journal_entry_id AND je.organization_id=a.organization_id AND je.status IN ('posted','reversed') AND je.entry_date<=%s WHERE a.organization_id=%s AND a.account_type IN ('revenue','expense') GROUP BY a.id ORDER BY a.code""",(d,organization_id))
 items=[{**dict(x),"balance":str((x["credit"]-x["debit"]) if x["account_type"]=="revenue" else (x["debit"]-x["credit"]))} for x in r]
 revenue=sum((x["credit"]-x["debit"] for x in r if x["account_type"]=="revenue"),0); expense=sum((x["debit"]-x["credit"] for x in r if x["account_type"]=="expense"),0)
 return {"as_of":None if as_of is None else as_of.isoformat(),"items":items,"revenue":str(revenue),"expense":str(expense),"net_profit":str(revenue-expense)}
@router.get("/{organization_id}/reports/balance-sheet")
def balance_sheet(organization_id:int,request:Request,as_of:date|None=Query(None),caller:Caller=Depends(require_accounting_caller)):
 d=as_of or date.max
 r=rows(request,"""SELECT a.id,a.code,a.name,a.account_type,COALESCE(SUM(jl.debit),0) debit,COALESCE(SUM(jl.credit),0) credit FROM accounts a LEFT JOIN journal_lines jl ON jl.account_id=a.id LEFT JOIN journal_entries je ON je.id=jl.journal_entry_id AND je.organization_id=a.organization_id AND je.status IN ('posted','reversed') AND je.entry_date<=%s WHERE a.organization_id=%s AND a.account_type IN ('asset','liability','equity') GROUP BY a.id ORDER BY a.code""",(d,organization_id))
 items=[]
 for x in r:
  bal=x["debit"]-x["credit"] if x["account_type"]=="asset" else x["credit"]-x["debit"]
  items.append({**dict(x),"balance":str(bal)})
 return {"as_of":None if as_of is None else as_of.isoformat(),"items":items}
@router.get("/{organization_id}/reports/account/{account_id}")
def account_statement(organization_id:int,account_id:int,request:Request,date_from:date|None=Query(None),date_to:date|None=Query(None),caller:Caller=Depends(require_accounting_caller)):
 params=[organization_id,account_id]; where="je.organization_id=%s AND jl.account_id=%s AND je.status IN ('posted','reversed')"
 if date_from: where+=" AND je.entry_date>=%s"; params.append(date_from)
 if date_to: where+=" AND je.entry_date<=%s"; params.append(date_to)
 return {"items":[dict(x) for x in rows(request,"SELECT je.id,je.document_no,je.entry_date,je.description,jl.debit,jl.credit FROM journal_entries je JOIN journal_lines jl ON jl.journal_entry_id=je.id WHERE "+where+" ORDER BY je.entry_date,je.id,jl.id",params)]}
