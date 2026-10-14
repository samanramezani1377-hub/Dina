from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.auth import issue_access_token
from src.business_store import BusinessStore, TenantStore
from src.financial_reports_api import _account_totals
from src.main import app


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
