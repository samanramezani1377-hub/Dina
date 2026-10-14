from __future__ import annotations
"""PostgreSQL tenant/SaaS repositories with an in-memory test implementation."""
from datetime import date
from decimal import Decimal
from typing import Any
import uuid
import psycopg
from psycopg.rows import dict_row
from .models import Organization, JournalLine
from .accounting import validate_journal

class TenantStore:
    def __init__(self, database_url: str | None = None):
        self._memory = database_url is None
        self.database_url = (database_url or "").replace("postgresql+psycopg://", "postgresql://", 1)
        self._orgs: dict[int, Organization] = {}
        self._memberships: dict[tuple[int, int], str] = {}
        self._next_org = 1
    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)
    @property
    def organizations(self) -> dict[int, Organization]:
        if self._memory:
            return dict(self._orgs)
        with self._connect() as conn:
            rows = conn.execute("SELECT id,name FROM organizations ORDER BY id").fetchall()
        return {int(r["id"]): Organization(int(r["id"]), r["name"]) for r in rows}
    def user_role(self, user_id: int, organization_id: int) -> str | None:
        if self._memory:
            return self._memberships.get((user_id, organization_id))
        with self._connect() as conn:
            row = conn.execute("SELECT role FROM memberships WHERE user_id=%s AND organization_id=%s", (user_id, organization_id)).fetchone()
        return None if row is None else str(row["role"])
    def owner_count(self, organization_id: int) -> int:
        if self._memory:
            return sum(1 for (uid, oid), role in self._memberships.items()
                       if oid == organization_id and role == "owner")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM memberships WHERE organization_id=%s AND role='owner'",
                (organization_id,),
            ).fetchone()
        return int(row["count"])

    def can_access(self, user_id: int, organization_id: int) -> bool:
        return self.user_role(user_id, organization_id) is not None
    def create_organization(self, name: str, user_id: int) -> Organization:
        name = name.strip()
        if self._memory:
            oid = self._next_org; self._next_org += 1
            org = Organization(oid, name)
            self._orgs[oid] = org
            self._memberships[(user_id, oid)] = "owner"
            return org
        with self._connect() as conn:
            row = conn.execute("INSERT INTO organizations(name) VALUES(%s) RETURNING id,name", (name,)).fetchone()
            conn.execute("INSERT INTO memberships(user_id,organization_id,role) VALUES(%s,%s,'owner')", (user_id, int(row["id"])))
        return Organization(int(row["id"]), row["name"])
    def add_membership(self, user_id: int, organization_id: int, role: str) -> None:
        if self._memory:
            if organization_id not in self._orgs:
                raise ValueError("organization does not exist")
            previous_role = self._memberships.get((user_id, organization_id))
            if previous_role == "owner" and role != "owner" and self.owner_count(organization_id) <= 1:
                raise ValueError("cannot demote the last organization owner")
            self._memberships[(user_id, organization_id)] = role
            return
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, role FROM memberships WHERE organization_id=%s FOR UPDATE",
                (organization_id,),
            ).fetchall()
            previous = next((row for row in rows if int(row["user_id"]) == user_id), None)
            owner_count = sum(row["role"] == "owner" for row in rows)
            if previous and previous["role"] == "owner" and role != "owner" and owner_count <= 1:
                raise ValueError("cannot demote the last organization owner")
            conn.execute(
                "INSERT INTO memberships(user_id,organization_id,role) VALUES(%s,%s,%s) "
                "ON CONFLICT (user_id,organization_id) DO UPDATE SET role=EXCLUDED.role",
                (user_id, organization_id, role),
            )
    def remove_membership(self, user_id: int, organization_id: int) -> None:
        if self._memory:
            role = self._memberships.get((user_id, organization_id))
            if role == "owner" and self.owner_count(organization_id) <= 1:
                raise ValueError("cannot remove the last organization owner")
            self._memberships.pop((user_id, organization_id), None)
            return
        # Lock all membership rows for this organization so two concurrent
        # removals cannot both observe two owners and remove both.
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, role FROM memberships WHERE organization_id=%s FOR UPDATE",
                (organization_id,),
            ).fetchall()
            target = next((row for row in rows if int(row["user_id"]) == user_id), None)
            if target is None:
                return
            if target["role"] == "owner" and sum(row["role"] == "owner" for row in rows) <= 1:
                raise ValueError("cannot remove the last organization owner")
            conn.execute(
                "DELETE FROM memberships WHERE user_id=%s AND organization_id=%s",
                (user_id, organization_id),
            )

class BusinessStore:
    def __init__(self, database_url: str | None = None):
        self._memory = database_url is None
        self.database_url = (database_url or "").replace("postgresql+psycopg://", "postgresql://", 1)
        self._customers: list[dict] = []; self._invoices: list[dict] = []
        self._payments: list[dict] = []; self._subscriptions: list[dict] = []; self._payment_keys: dict[tuple[int,str], int] = {}
        self._ids = {"customer": 1, "invoice": 1, "payment": 1, "subscription": 1}
    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)
    def customer(self, org: int, customer_id: int):
        if self._memory:
            return next((x for x in self._customers if x["id"] == customer_id and x["organization_id"] == org), None)
        with self._connect() as conn:
            return conn.execute("SELECT * FROM customers WHERE id=%s AND organization_id=%s", (customer_id, org)).fetchone()
    def create_customer(self, org: int, name: str, email: str | None, phone: str | None):
        if self._memory:
            x={"id":self._ids["customer"],"organization_id":org,"name":name,"email":email,"phone":phone}
            self._ids["customer"] += 1; self._customers.append(x); return x
        with self._connect() as conn:
            return conn.execute("INSERT INTO customers(organization_id,name,email,phone) VALUES(%s,%s,%s,%s) RETURNING *",(org,name,email,phone)).fetchone()
    def list_customers(self, org: int):
        if self._memory: return [x for x in self._customers if x["organization_id"] == org]
        with self._connect() as conn: return conn.execute("SELECT * FROM customers WHERE organization_id=%s ORDER BY id",(org,)).fetchall()
    def create_invoice(
        self,
        org: int,
        customer_id: int,
        number: str,
        total: Decimal,
        issue_date: date,
        due_date: date | None,
        receivable_account_id: int,
        revenue_account_id: int,
    ):
        if total <= 0:
            raise ValueError("invoice total must be greater than zero")
        if self._memory:
            if self.customer(org, customer_id) is None:
                raise KeyError("customer")
            if receivable_account_id == revenue_account_id:
                raise ValueError("receivable and revenue accounts must be different")
            x = {
                "id": self._ids["invoice"],
                "organization_id": org,
                "customer_id": customer_id,
                "invoice_no": number,
                "issue_date": issue_date,
                "due_date": due_date,
                "total": total,
                "paid": Decimal("0"),
                "status": "open",
                "receivable_account_id": receivable_account_id,
                "revenue_account_id": revenue_account_id,
                "journal_entry_id": None,
            }
            self._ids["invoice"] += 1
            self._invoices.append(x)
            return x

        if receivable_account_id == revenue_account_id:
            raise ValueError("receivable and revenue accounts must be different")
        with self._connect() as conn:
            customer = conn.execute(
                "SELECT id FROM customers WHERE id=%s AND organization_id=%s FOR SHARE",
                (customer_id, org),
            ).fetchone()
            if customer is None:
                raise KeyError("customer")
            accounts = conn.execute(
                """SELECT id, account_type FROM accounts
                   WHERE organization_id=%s AND id IN (%s,%s) FOR SHARE""",
                (org, receivable_account_id, revenue_account_id),
            ).fetchall()
            by_id = {int(row["id"]): row for row in accounts}
            if len(by_id) != 2:
                raise KeyError("account")
            if by_id[receivable_account_id]["account_type"] != "asset":
                raise ValueError("receivable account must be an asset account")
            if by_id[revenue_account_id]["account_type"] != "revenue":
                raise ValueError("revenue account must be a revenue account")

            fiscal_year = conn.execute(
                """SELECT id FROM fiscal_years
                   WHERE organization_id=%s AND status='open'
                     AND starts_on<=%s AND ends_on>=%s
                   FOR UPDATE""",
                (org, issue_date, issue_date),
            ).fetchone()
            if fiscal_year is None:
                raise ValueError("no open fiscal year covers this invoice date")

            lines = [
                JournalLine(receivable_account_id, total, Decimal("0")),
                JournalLine(revenue_account_id, Decimal("0"), total),
            ]
            validate_journal(lines)
            invoice = conn.execute(
                """INSERT INTO invoices
                   (organization_id,customer_id,invoice_no,issue_date,due_date,total,
                    receivable_account_id,revenue_account_id)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (org, customer_id, number, issue_date, due_date, total,
                 receivable_account_id, revenue_account_id),
            ).fetchone()
            journal = conn.execute(
                """INSERT INTO journal_entries
                   (organization_id,document_no,description,status,entry_date,posted_at)
                   VALUES(%s,%s,%s,'posted',%s,NOW()) RETURNING id""",
                (org, f"INV-{number}", f"Invoice {number}", issue_date),
            ).fetchone()
            journal_id = int(journal["id"])
            for line in lines:
                conn.execute(
                    """INSERT INTO journal_lines(journal_entry_id,account_id,debit,credit)
                       VALUES(%s,%s,%s,%s)""",
                    (journal_id, line.account_id, line.debit, line.credit),
                )
            return conn.execute(
                """UPDATE invoices SET journal_entry_id=%s
                   WHERE id=%s AND organization_id=%s RETURNING *""",
                (journal_id, invoice["id"], org),
            ).fetchone()
    def list_invoices(self, org: int):
        if self._memory: return [x for x in self._invoices if x["organization_id"] == org]
        with self._connect() as conn: return conn.execute("SELECT * FROM invoices WHERE organization_id=%s ORDER BY id",(org,)).fetchall()
    def invoice(self, org: int, invoice_id: int):
        if self._memory: return next((x for x in self._invoices if x["id"] == invoice_id and x["organization_id"] == org), None)
        with self._connect() as conn: return conn.execute("SELECT * FROM invoices WHERE id=%s AND organization_id=%s",(invoice_id,org)).fetchone()
    def record_payment(
        self,
        org: int,
        invoice_id: int,
        amount: Decimal,
        method: str,
        reference: str | None,
        idempotency_key: str | None = None,
        cash_account_id: int | None = None,
        receivable_account_id: int | None = None,
    ):
        """Record a payment and its cash/receivable journal atomically."""
        if cash_account_id is None or receivable_account_id is None:
            raise ValueError("cash_account_id and receivable_account_id are required for accounting")
        if self._memory:
            inv = self.invoice(org, invoice_id)
            if inv is None:
                raise KeyError("invoice")
            if inv.get("receivable_account_id") != receivable_account_id:
                raise ValueError("payment receivable account must match the invoice account")
            if idempotency_key:
                existing_id = self._payment_keys.get((org, idempotency_key))
                if existing_id is not None:
                    existing = next(p for p in self._payments if p["id"] == existing_id)
                    if (
                        existing["invoice_id"] != invoice_id
                        or Decimal(existing["amount"]) != amount
                        or existing["method"] != method
                        or existing["reference"] != reference
                        or existing["cash_account_id"] != cash_account_id
                        or existing["receivable_account_id"] != receivable_account_id
                    ):
                        raise ValueError("Idempotency-Key was already used with different payment details")
                    existing_invoice = self.invoice(org, int(existing["invoice_id"]))
                    if existing_invoice is None:
                        raise KeyError("invoice")
                    return existing, existing_invoice
            if amount <= 0 or amount > Decimal(inv["total"]) - Decimal(inv["paid"]):
                raise ValueError("payment exceeds invoice balance")
            payment = {
                "id": self._ids["payment"],
                "organization_id": org,
                "invoice_id": invoice_id,
                "amount": amount,
                "method": method,
                "reference": reference,
                "cash_account_id": cash_account_id,
                "receivable_account_id": receivable_account_id,
                "journal_entry_id": None,
            }
            self._ids["payment"] += 1
            self._payments.append(payment)
            if idempotency_key:
                self._payment_keys[(org, idempotency_key)] = payment["id"]
            inv["paid"] = Decimal(inv["paid"]) + amount
            inv["status"] = "paid" if inv["paid"] == inv["total"] else "partial"
            return payment, inv

        with self._connect() as conn:
            if idempotency_key:
                conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s), %s)",
                    (idempotency_key, org),
                )
                existing = conn.execute(
                    """SELECT payment_id FROM payment_idempotency
                       WHERE organization_id=%s AND idempotency_key=%s FOR SHARE""",
                    (org, idempotency_key),
                ).fetchone()
                if existing:
                    payment = conn.execute(
                        "SELECT * FROM payments WHERE id=%s AND organization_id=%s",
                        (existing["payment_id"], org),
                    ).fetchone()
                    if payment is None:
                        raise KeyError("payment")
                    inv = conn.execute(
                        "SELECT * FROM invoices WHERE id=%s AND organization_id=%s",
                        (payment["invoice_id"], org),
                    ).fetchone()
                    cash_transaction = conn.execute(
                        "SELECT cash_account_id FROM cash_transactions WHERE journal_entry_id=%s",
                        (payment["journal_entry_id"],),
                    ).fetchone() if payment["journal_entry_id"] is not None else None
                    if inv is None:
                        raise KeyError("invoice")
                    if (
                        int(payment["invoice_id"]) != invoice_id
                        or Decimal(payment["amount"]) != amount
                        or payment["method"] != method
                        or payment["reference"] != reference
                        or int(inv["receivable_account_id"] or 0) != receivable_account_id
                        or cash_transaction is None
                        or int(cash_transaction["cash_account_id"]) != cash_account_id
                    ):
                        raise ValueError("Idempotency-Key was already used with different payment details")
                    return payment, inv

            inv = conn.execute(
                "SELECT * FROM invoices WHERE id=%s AND organization_id=%s FOR UPDATE",
                (invoice_id, org),
            ).fetchone()
            if inv is None:
                raise KeyError("invoice")
            if inv["journal_entry_id"] is None or inv["receivable_account_id"] is None:
                raise ValueError("invoice must have a posted accounting entry before payment")
            if int(inv["receivable_account_id"]) != receivable_account_id:
                raise ValueError("payment receivable account must match the invoice account")
            remaining = Decimal(inv["total"]) - Decimal(inv["paid"])
            if amount <= 0 or amount > remaining:
                raise ValueError("payment exceeds invoice balance")

            cash = conn.execute(
                "SELECT * FROM cash_accounts WHERE id=%s AND organization_id=%s FOR UPDATE",
                (cash_account_id, org),
            ).fetchone()
            if cash is None:
                raise KeyError("cash_account")
            if cash["account_id"] is None:
                raise ValueError("cash account is not linked to a chart-of-accounts account")
            accounts = conn.execute(
                """SELECT id,account_type FROM accounts
                   WHERE id IN (%s,%s) AND organization_id=%s""",
                (cash["account_id"], receivable_account_id, org),
            ).fetchall()
            by_id = {int(row["id"]): row for row in accounts}
            if len(by_id) != 2:
                raise KeyError("account")
            if by_id[int(cash["account_id"])]["account_type"] != "asset":
                raise ValueError("cash account must link to an asset account")
            if by_id[receivable_account_id]["account_type"] != "asset":
                raise ValueError("receivable account must be an asset account")

            fiscal_year = conn.execute(
                """SELECT id FROM fiscal_years
                   WHERE organization_id=%s AND status='open'
                     AND starts_on<=CURRENT_DATE AND ends_on>=CURRENT_DATE
                   FOR UPDATE""",
                (org,),
            ).fetchone()
            if fiscal_year is None:
                raise ValueError("no open fiscal year covers this payment date")

            lines = [
                JournalLine(int(cash["account_id"]), amount, Decimal("0")),
                JournalLine(receivable_account_id, Decimal("0"), amount),
            ]
            validate_journal(lines)
            journal = conn.execute(
                """INSERT INTO journal_entries
                   (organization_id,document_no,description,status,entry_date,posted_at)
                   VALUES (%s,%s,%s,'posted',CURRENT_DATE,NOW()) RETURNING id""",
                (org, f"PAY-{invoice_id}-{uuid.uuid4().hex[:12]}", f"Payment for invoice {inv['invoice_no']}"),
            ).fetchone()
            journal_id = int(journal["id"])
            for line in lines:
                conn.execute(
                    """INSERT INTO journal_lines(journal_entry_id,account_id,debit,credit)
                       VALUES(%s,%s,%s,%s)""",
                    (journal_id, line.account_id, line.debit, line.credit),
                )

            payment = conn.execute(
                """INSERT INTO payments
                   (organization_id,invoice_id,amount,method,reference,journal_entry_id)
                   VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",
                (org, invoice_id, amount, method, reference, journal_id),
            ).fetchone()
            if idempotency_key:
                conn.execute(
                    """INSERT INTO payment_idempotency(organization_id,idempotency_key,payment_id)
                       VALUES(%s,%s,%s)""",
                    (org, idempotency_key, payment["id"]),
                )
            paid = Decimal(inv["paid"]) + amount
            status = "paid" if paid == Decimal(inv["total"]) else "partial"
            updated = conn.execute(
                """UPDATE invoices SET paid=%s,status=%s
                   WHERE id=%s AND organization_id=%s RETURNING *""",
                (paid, status, invoice_id, org),
            ).fetchone()
            conn.execute(
                """INSERT INTO cash_transactions
                   (organization_id,cash_account_id,amount,direction,description,reference,
                    transaction_date,journal_entry_id)
                   VALUES(%s,%s,%s,'in',%s,%s,CURRENT_DATE,%s)""",
                (org, cash_account_id, amount, f"Payment for invoice {inv['invoice_no']}", reference, journal_id),
            )
            return payment, updated

    def subscription(self, org: int):
        if self._memory: return next((x for x in reversed(self._subscriptions) if x["organization_id"] == org), None)
        with self._connect() as conn: return conn.execute("SELECT * FROM subscriptions WHERE organization_id=%s ORDER BY id DESC LIMIT 1",(org,)).fetchone()
    def upsert_subscription(self, org: int, plan: str, status: str, starts_at: Any, ends_at: Any):
        if self._memory:
            x={"id":self._ids["subscription"],"organization_id":org,"plan":plan,"status":status,"starts_at":starts_at,"ends_at":ends_at}
            self._ids["subscription"] += 1; self._subscriptions.append(x); return x
        with self._connect() as conn:
            conn.execute("UPDATE subscriptions SET status='expired' WHERE organization_id=%s AND status IN ('trial','active')",(org,))
            return conn.execute("INSERT INTO subscriptions(organization_id,plan,status,starts_at,ends_at) VALUES(%s,%s,%s,%s,%s) RETURNING *",(org,plan,status,starts_at,ends_at)).fetchone()
