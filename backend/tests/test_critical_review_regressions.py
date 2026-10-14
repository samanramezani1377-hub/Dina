import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.auth import issue_access_token
from src.business_store import BusinessStore, TenantStore
from src.financial_reports_api import _account_totals
from src.main import app
from src.payment_api import _complete_verified_attempt


def test_financial_report_query_filters_entries_before_aggregating(monkeypatch):
    captured = {}

    def fake_rows(request, sql, args):
        captured["sql"] = sql
        captured["args"] = args
        return []

    monkeypatch.setattr("src.financial_reports_api.rows", fake_rows)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(database_url="postgresql://unused")
            )
        )
    )

    _account_totals(request, 7, date(2026, 10, 1), ("revenue", "expense"))

    sql = " ".join(captured["sql"].lower().split())
    assert "je.status = 'posted'" in sql
    assert "je.entry_date <= %s" in sql
    assert "jl.journal_entry_id = je.id" in sql
    assert "jl.account_id = a.id" in sql
    assert captured["args"] == (date(2026, 10, 1), 7, "revenue", "expense")
    # This was the broken shape: it aggregated lines first and merely attached
    # a filtered journal entry with a LEFT JOIN, which doesn't filter SUM(jl.*).
    assert "left join journal_lines jl on jl.account_id=a.id" not in sql


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires PostgreSQL")
def test_financial_report_totals_exclude_drafts_and_future_entries():
    database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(database_url) as connection:
        # Some earlier persistence tests truncate rows without resetting the
        # serial sequence. Bring it forward before creating an integration row.
        connection.execute(
            """SELECT setval(
                 pg_get_serial_sequence('organizations','id'),
                 GREATEST(COALESCE((SELECT MAX(id) FROM organizations),1),1)
               )"""
        )
        organization_id = connection.execute(
            "INSERT INTO organizations(name) VALUES (%s) RETURNING id",
            (f"report-regression-{uuid4()}",),
        ).fetchone()[0]
        account_id = connection.execute(
            """INSERT INTO accounts(organization_id,code,name,account_type)
               VALUES (%s,'REV-TEST','Revenue test','revenue') RETURNING id""",
            (organization_id,),
        ).fetchone()[0]
        entry_ids = []
        for number, status, entry_date, amount in (
            ("POSTED-IN-RANGE", "posted", date(2026, 1, 10), Decimal("100")),
            ("DRAFT-IN-RANGE", "draft", date(2026, 2, 10), Decimal("50")),
            ("POSTED-FUTURE", "posted", date(2026, 12, 10), Decimal("25")),
        ):
            entry_id = connection.execute(
                """INSERT INTO journal_entries
                   (organization_id,document_no,description,status,entry_date,posted_at)
                   VALUES (%s,%s,%s,%s,%s,CASE WHEN %s='posted' THEN NOW() ELSE NULL END)
                   RETURNING id""",
                (organization_id, number, number, status, entry_date, status),
            ).fetchone()[0]
            entry_ids.append(entry_id)
            connection.execute(
                "INSERT INTO journal_lines(journal_entry_id,account_id,debit,credit) VALUES (%s,%s,0,%s)",
                (entry_id, account_id, amount),
            )

    try:
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(settings=SimpleNamespace(database_url=database_url))
            )
        )
        totals = _account_totals(request, organization_id, date(2026, 6, 30), ("revenue",))
        assert len(totals) == 1
        assert Decimal(totals[0]["credit"]) == Decimal("100")
        assert Decimal(totals[0]["debit"]) == Decimal("0")
    finally:
        # Keep the shared CI database isolated for the persistence test, which
        # resets organizations before exercising the durable store.
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """DELETE FROM journal_lines
                   WHERE journal_entry_id IN
                     (SELECT id FROM journal_entries WHERE organization_id=%s)""",
                (organization_id,),
            )
            connection.execute("DELETE FROM journal_entries WHERE organization_id=%s", (organization_id,))
            connection.execute("DELETE FROM accounts WHERE organization_id=%s", (organization_id,))
            connection.execute("DELETE FROM organizations WHERE id=%s", (organization_id,))


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires PostgreSQL")
def test_verified_payment_renews_subscription_once():
    database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    suffix = str(uuid4())
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """SELECT setval(
                 pg_get_serial_sequence('organizations','id'),
                 GREATEST(COALESCE((SELECT MAX(id) FROM organizations),1),1)
               )"""
        )
        organization_id = connection.execute(
            "INSERT INTO organizations(name) VALUES (%s) RETURNING id",
            (f"payment-regression-{suffix}",),
        ).fetchone()[0]
        plan_code = f"payment-test-{suffix}"
        connection.execute(
            """INSERT INTO plans(code,name,price,currency,billing_period)
               VALUES (%s,'Payment regression',100,'IRR','month')""",
            (plan_code,),
        )
        subscription_id = connection.execute(
            """INSERT INTO subscriptions
               (organization_id,plan,status,starts_at,ends_at)
               VALUES (%s,%s,'expired',NOW()-INTERVAL '2 months',NOW()-INTERVAL '1 day')
               RETURNING id""",
            (organization_id, plan_code),
        ).fetchone()[0]
        authority = f"authority-{suffix}"
        attempt_id = connection.execute(
            """INSERT INTO payment_attempts
               (organization_id,provider,idempotency_key,provider_reference,amount,currency,status,subscription_id,metadata)
               VALUES (%s,'zarinpal',%s,%s,100,'IRR','pending',%s,'{}'::jsonb)
               RETURNING id""",
            (organization_id, f"idem-{suffix}", authority, subscription_id),
        ).fetchone()[0]

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=SimpleNamespace(database_url=database_url))
        )
    )
    try:
        first = _complete_verified_attempt(
            request, attempt_id, organization_id, authority,
            {"ref_id": f"ref-{suffix}", "verified_code": 100},
        )
        assert first["status"] == "succeeded"
        with psycopg.connect(database_url) as connection:
            subscription = connection.execute(
                "SELECT status,ends_at FROM subscriptions WHERE id=%s",
                (subscription_id,),
            ).fetchone()
            assert subscription[0] == "active"
            assert subscription[1] is not None
            assert subscription[1].date() > date.today()
            assert connection.execute(
                "SELECT COUNT(*) FROM subscription_history WHERE subscription_id=%s AND action='payment_verified'",
                (subscription_id,),
            ).fetchone()[0] == 1

        # A duplicate callback must be idempotent and must not extend the term twice.
        _complete_verified_attempt(
            request, attempt_id, organization_id, authority,
            {"ref_id": f"ref-{suffix}", "verified_code": 100},
        )
        with psycopg.connect(database_url) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM subscription_history WHERE subscription_id=%s AND action='payment_verified'",
                (subscription_id,),
            ).fetchone()[0] == 1
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute("DELETE FROM subscription_history WHERE organization_id=%s", (organization_id,))
            connection.execute("DELETE FROM payment_attempts WHERE id=%s", (attempt_id,))
            connection.execute("DELETE FROM subscriptions WHERE id=%s", (subscription_id,))
            connection.execute("DELETE FROM plans WHERE code=%s", (plan_code,))
            connection.execute("DELETE FROM organizations WHERE id=%s", (organization_id,))


def test_only_managers_can_manage_members_and_managers_cannot_grant_owner():
    with TestClient(app) as client:
        tenant = TenantStore()
        app.state.memberships = tenant
        app.state.business_store = BusinessStore()
        owner = tenant.create_organization("Role regression", 501)
        tenant.add_membership(502, owner.id, "manager")
        tenant.add_membership(503, owner.id, "viewer")

        manager_headers = {
            "Authorization": f"Bearer {issue_access_token(502)}",
        }
        viewer_headers = {
            "Authorization": f"Bearer {issue_access_token(503)}",
        }

        forbidden_owner_grant = client.post(
            f"/api/v1/organizations/{owner.id}/members",
            params={"member_user_id": 504, "role": "owner"},
            headers=manager_headers,
        )
        assert forbidden_owner_grant.status_code == 403

        forbidden_owner_demotion = client.post(
            f"/api/v1/organizations/{owner.id}/members",
            params={"member_user_id": 501, "role": "manager"},
            headers=manager_headers,
        )
        assert forbidden_owner_demotion.status_code == 403

        forbidden_customer_write = client.post(
            f"/api/v1/organizations/{owner.id}/customers",
            headers=viewer_headers,
            json={"name": "Should not be created"},
        )
        assert forbidden_customer_write.status_code == 403


def test_last_organization_owner_cannot_be_removed():
    with TestClient(app) as client:
        tenant = TenantStore()
        app.state.memberships = tenant
        owner = tenant.create_organization("Last owner regression", 601)
        response = client.delete(
            f"/api/v1/organizations/{owner.id}/members/601",
            headers={"Authorization": f"Bearer {issue_access_token(601)}"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
