import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from src.models import DRAFT, POSTED, JournalLine
from src.postgres_store import PostgresStore


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires PostgreSQL")
def test_postgres_store_persists_and_enforces_tenant_scope():
    store = PostgresStore(os.environ["DATABASE_URL"])
    with psycopg.connect(store.database_url) as conn:
        conn.execute("DELETE FROM organizations")
        org1 = conn.execute(
            "INSERT INTO organizations(name) VALUES ('Dina test one') RETURNING id"
        ).fetchone()[0]
        org2 = conn.execute(
            "INSERT INTO organizations(name) VALUES ('Dina test two') RETURNING id"
        ).fetchone()[0]

    cash = store.add_account(org1, "1100", "Cash", "asset")
    revenue = store.add_account(org1, "4100", "Revenue", "revenue")

    entry = store.add_entry(
        org1,
        "JV-PERSIST-1",
        "persistent sale",
        date(2026, 10, 1),
        [
            JournalLine(cash.id, Decimal("100"), Decimal("0")),
            JournalLine(revenue.id, Decimal("0"), Decimal("100")),
        ],
        status=DRAFT,
    )
    assert store.get_entry(org1, entry.id).document_no == "JV-PERSIST-1"

    store.post_entry(org1, entry.id)
    assert store.get_entry(org1, entry.id).status == POSTED

    with pytest.raises(Exception) as exc:
        store.get_account(org2, cash.id)
    assert getattr(exc.value, "code", None) == "account_not_found"

    with psycopg.connect(store.database_url) as conn:
        assert conn.execute(
            "SELECT count(*) FROM journal_entries WHERE id=%s", (entry.id,)
        ).fetchone()[0] == 1
