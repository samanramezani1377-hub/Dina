from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request

from .errors import ApiError, ErrorCode
from .identity import Caller
from .ledger_api import require_accounting_caller

router = APIRouter(prefix="/api/v1/organizations", tags=["financial-reports"])


def rows(request: Request, sql: str, args: tuple | list) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row

    database_url = request.app.state.settings.database_url.replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return connection.execute(sql, args).fetchall()


def _as_of(value: date | None) -> date:
    return value or date.max


def _check_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "date_from must be on or before date_to",
            {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        )


def _account_totals(request: Request, organization_id: int, as_of: date, account_types: tuple[str, ...]) -> list[dict]:
    placeholders = ",".join(["%s"] * len(account_types))
    # Filter journal entries before joining lines. Putting the status/date
    # predicates on a LEFT JOIN from journal_lines leaves unmatched lines in
    # the SUM and silently includes drafts and out-of-period entries.
    sql = f"""
        SELECT a.id, a.code, a.name, a.account_type,
               COALESCE(SUM(jl.debit), 0) AS debit,
               COALESCE(SUM(jl.credit), 0) AS credit
        FROM accounts AS a
        LEFT JOIN journal_entries AS je
          ON je.organization_id = a.organization_id
         AND je.status = 'posted'
         AND je.entry_date <= %s
        LEFT JOIN journal_lines AS jl
          ON jl.journal_entry_id = je.id
         AND jl.account_id = a.id
        WHERE a.organization_id = %s
          AND a.account_type IN ({placeholders})
        GROUP BY a.id, a.code, a.name, a.account_type
        ORDER BY a.code
    """
    return rows(request, sql, (as_of, organization_id, *account_types))


@router.get("/{organization_id}/reports/profit-loss")
def profit_loss(
    organization_id: int,
    request: Request,
    as_of: date | None = Query(None),
    caller: Caller = Depends(require_accounting_caller),
):
    result = _account_totals(request, organization_id, _as_of(as_of), ("revenue", "expense"))
    items = []
    revenue = Decimal("0")
    expense = Decimal("0")
    for row in result:
        debit, credit = Decimal(row["debit"]), Decimal(row["credit"])
        balance = credit - debit if row["account_type"] == "revenue" else debit - credit
        items.append({**dict(row), "balance": str(balance)})
        if row["account_type"] == "revenue":
            revenue += credit - debit
        else:
            expense += debit - credit
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "items": items,
        "revenue": str(revenue),
        "expense": str(expense),
        "net_profit": str(revenue - expense),
    }


@router.get("/{organization_id}/reports/balance-sheet")
def balance_sheet(
    organization_id: int,
    request: Request,
    as_of: date | None = Query(None),
    caller: Caller = Depends(require_accounting_caller),
):
    result = _account_totals(request, organization_id, _as_of(as_of), ("asset", "liability", "equity"))
    items = []
    for row in result:
        debit, credit = Decimal(row["debit"]), Decimal(row["credit"])
        balance = debit - credit if row["account_type"] == "asset" else credit - debit
        items.append({**dict(row), "balance": str(balance)})
    return {"as_of": as_of.isoformat() if as_of else None, "items": items}


@router.get("/{organization_id}/reports/account/{account_id}")
def account_statement(
    organization_id: int,
    account_id: int,
    request: Request,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    caller: Caller = Depends(require_accounting_caller),
):
    _check_date_range(date_from, date_to)
    clauses = [
        "je.organization_id = %s",
        "jl.account_id = %s",
        "a.organization_id = je.organization_id",
        "je.status = 'posted'",
    ]
    params: list[object] = [organization_id, account_id]
    if date_from is not None:
        clauses.append("je.entry_date >= %s")
        params.append(date_from)
    if date_to is not None:
        clauses.append("je.entry_date <= %s")
        params.append(date_to)
    return {
        "items": [
            dict(row)
            for row in rows(
                request,
                """SELECT je.id, je.document_no, je.entry_date, je.description,
                          jl.debit, jl.credit
                   FROM journal_entries AS je
                   JOIN journal_lines AS jl ON jl.journal_entry_id = je.id
                   JOIN accounts AS a ON a.id = jl.account_id
                   WHERE """ + " AND ".join(clauses) + """
                   ORDER BY je.entry_date, je.id, jl.id""",
                params,
            )
        ]
    }


@router.get("/{organization_id}/reports/trial-balance")
def trial_balance(
    organization_id: int,
    request: Request,
    as_of: date | None = Query(None),
    caller: Caller = Depends(require_accounting_caller),
):
    result = _account_totals(
        request, organization_id, _as_of(as_of),
        ("asset", "liability", "equity", "revenue", "expense"),
    )
    total_debit = sum((Decimal(row["debit"]) for row in result), Decimal("0"))
    total_credit = sum((Decimal(row["credit"]) for row in result), Decimal("0"))
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "items": [dict(row) for row in result],
        "total_debit": str(total_debit),
        "total_credit": str(total_credit),
    }


@router.get("/{organization_id}/reports/inventory")
def inventory_report(
    organization_id: int,
    request: Request,
    warehouse_id: int | None = None,
    product_id: int | None = None,
    caller: Caller = Depends(require_accounting_caller),
):
    params: list[object] = [organization_id]
    where = ["sm.organization_id = %s", "p.organization_id = sm.organization_id",
             "w.organization_id = sm.organization_id"]
    if warehouse_id is not None:
        where.append("sm.warehouse_id = %s")
        params.append(warehouse_id)
    if product_id is not None:
        where.append("sm.product_id = %s")
        params.append(product_id)
    result = rows(
        request,
        """SELECT sm.warehouse_id, sm.product_id, p.name AS product_name,
                  w.name AS warehouse_name, COALESCE(SUM(sm.quantity), 0) AS quantity,
                  COALESCE(SUM(sm.quantity * sm.unit_cost), 0) AS stock_value,
                  COALESCE(SUM(CASE WHEN sm.quantity > 0
                    THEN sm.quantity * sm.unit_cost ELSE 0 END), 0) AS received_value
           FROM stock_movements AS sm
           JOIN products AS p ON p.id = sm.product_id
           JOIN warehouses AS w ON w.id = sm.warehouse_id
           WHERE """ + " AND ".join(where) + """
           GROUP BY sm.warehouse_id, sm.product_id, p.name, w.name
           ORDER BY w.name, p.name""",
        params,
    )
    return {"items": [dict(row) for row in result]}


@router.get("/{organization_id}/reports/sales-summary")
def sales_summary(
    organization_id: int,
    request: Request,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    caller: Caller = Depends(require_accounting_caller),
):
    _check_date_range(date_from, date_to)
    params: list[object] = [organization_id]
    where = ["organization_id = %s", "status = 'posted'"]
    if date_from is not None:
        where.append("issue_date >= %s")
        params.append(date_from)
    if date_to is not None:
        where.append("issue_date <= %s")
        params.append(date_to)
    result = rows(
        request,
        """SELECT COUNT(*) AS documents, COALESCE(SUM(subtotal), 0) AS subtotal,
                  COALESCE(SUM(discount), 0) AS discount, COALESCE(SUM(tax), 0) AS tax,
                  COALESCE(SUM(total), 0) AS total
           FROM sales WHERE """ + " AND ".join(where),
        params,
    )
    return dict(result[0])


@router.get("/{organization_id}/reports/purchases-summary")
def purchases_summary(
    organization_id: int,
    request: Request,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    caller: Caller = Depends(require_accounting_caller),
):
    _check_date_range(date_from, date_to)
    params: list[object] = [organization_id]
    where = ["organization_id = %s", "status = 'posted'"]
    if date_from is not None:
        where.append("issue_date >= %s")
        params.append(date_from)
    if date_to is not None:
        where.append("issue_date <= %s")
        params.append(date_to)
    result = rows(
        request,
        """SELECT COUNT(*) AS documents, COALESCE(SUM(subtotal), 0) AS subtotal,
                  COALESCE(SUM(discount), 0) AS discount, COALESCE(SUM(tax), 0) AS tax,
                  COALESCE(SUM(total), 0) AS total
           FROM purchases WHERE """ + " AND ".join(where),
        params,
    )
    return dict(result[0])
