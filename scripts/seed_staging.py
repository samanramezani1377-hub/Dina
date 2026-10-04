"""Idempotent staging data for Dina's persistent test environment."""
from __future__ import annotations
import os
from datetime import date
from decimal import Decimal
import psycopg
from backend.src.security import hash_password

EMAIL = os.getenv("STAGING_TEST_EMAIL", "dina.test@example.com").strip().lower()
PASSWORD = os.getenv("STAGING_TEST_PASSWORD", "Dina-Test-2026!")
ORG_NAME = "دینا - سازمان تست"
ACCOUNTS = [
    ("1000", "صندوق", "asset"),
    ("1100", "بانک", "asset"),
    ("1200", "حساب‌های دریافتنی", "asset"),
    ("4000", "درآمد فروش", "revenue"),
]

def dsn() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)

def main() -> None:
    if os.getenv("ENVIRONMENT") != "staging" or os.getenv("STAGING_SEED_ENABLED") != "true":
        print("staging seed disabled")
        return
    if len(PASSWORD) < 12:
        raise SystemExit("STAGING_TEST_PASSWORD must be at least 12 characters")
    with psycopg.connect(dsn()) as conn:
        user = conn.execute("SELECT id FROM users WHERE email=%s", (EMAIL,)).fetchone()
        if user is None:
            user = conn.execute(
                "INSERT INTO users(email,password_hash,is_active) VALUES (%s,%s,true) RETURNING id",
                (EMAIL, hash_password(PASSWORD)),
            ).fetchone()
        user_id = int(user[0])

        org = conn.execute(
            "SELECT id FROM organizations WHERE name=%s ORDER BY id LIMIT 1", (ORG_NAME,)
        ).fetchone()
        if org is None:
            org = conn.execute("INSERT INTO organizations(name) VALUES(%s) RETURNING id", (ORG_NAME,)).fetchone()
        org_id = int(org[0])

        conn.execute(
            """INSERT INTO memberships(user_id,organization_id,role)
               VALUES(%s,%s,'owner')
               ON CONFLICT (user_id,organization_id) DO UPDATE SET role='owner'""",
            (user_id, org_id),
        )

        account_ids = {}
        for code, name, account_type in ACCOUNTS:
            row = conn.execute(
                "SELECT id FROM accounts WHERE organization_id=%s AND code=%s", (org_id, code)
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """INSERT INTO accounts(organization_id,code,name,account_type)
                       VALUES(%s,%s,%s,%s) RETURNING id""",
                    (org_id, code, name, account_type),
                ).fetchone()
            account_ids[code] = int(row[0])

        existing = conn.execute(
            "SELECT id FROM journal_entries WHERE organization_id=%s AND document_no='STAGING-001'",
            (org_id,),
        ).fetchone()
        if existing is None:
            entry = conn.execute(
                """INSERT INTO journal_entries
                   (organization_id,document_no,description,status,entry_date,posted_at)
                   VALUES(%s,'STAGING-001','دریافت وجه آزمایشی','posted',%s,NOW())
                   RETURNING id""",
                (org_id, date(2026, 10, 1)),
            ).fetchone()
            entry_id = int(entry[0])
            conn.execute(
                """INSERT INTO journal_lines(journal_entry_id,account_id,debit,credit)
                   VALUES(%s,%s,%s,%s),(%s,%s,%s,%s)""",
                (entry_id, account_ids["1100"], Decimal("1250.00"), Decimal("0"),
                 entry_id, account_ids["4000"], Decimal("0"), Decimal("1250.00")),
            )
        print(f"staging seed ready: user_id={user_id} organization_id={org_id}")

if __name__ == "__main__":
    main()
