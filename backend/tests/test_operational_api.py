from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient

from src.accounting_store import AccountingStore
from src.auth import issue_access_token
from src.business_store import BusinessStore, TenantStore
from src.main import app

def test_operational_api_covers_accounting_and_saas():
    with TestClient(app) as client:
        tenant = TenantStore()
        accounting = AccountingStore()
        business = BusinessStore()
        app.state.memberships = tenant
        app.state.accounting_store = accounting
        app.state.business_store = business

        user_id = 101
        org = tenant.create_organization("Dina Test", user_id)
        accounting.add_organization(org.id)
        token = issue_access_token(user_id)
        headers = {"Authorization": f"Bearer {token}"}

        cash = accounting.add_account(org.id, "1100", "Cash", "asset")
        revenue = accounting.add_account(org.id, "4000", "Revenue", "revenue")

        created = client.post(
            f"/api/v1/organizations/{org.id}/journals",
            headers=headers,
            json={
                "document_no": "J-1",
                "description": "sale",
                "entry_date": "2026-10-01",
                "lines": [
                    {"account_id": cash.id, "debit": "100.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "100.00"},
                ],
            },
        )
        assert created.status_code == 201, created.text
        entry_id = created.json()["id"]

        posted = client.post(
            f"/api/v1/organizations/{org.id}/journals/{entry_id}/post",
            headers=headers,
        )
        assert posted.status_code == 200, posted.text
        assert posted.json()["status"] == "posted"

        customer = client.post(
            f"/api/v1/organizations/{org.id}/customers",
            headers=headers,
            json={"name": "Customer One", "email": "customer@example.com"},
        )
        assert customer.status_code == 201, customer.text
        customer_id = customer.json()["id"]

        invoice = client.post(
            f"/api/v1/organizations/{org.id}/invoices",
            headers=headers,
            json={
                "customer_id": customer_id,
                "invoice_no": "INV-1",
                "total": "100.00",
                "issue_date": "2026-10-01",
            },
        )
        assert invoice.status_code == 201, invoice.text
        invoice_id = invoice.json()["id"]

        payment = client.post(
            f"/api/v1/organizations/{org.id}/invoices/{invoice_id}/payments",
            headers=headers,
            json={"amount": "100.00", "method": "bank"},
        )
        assert payment.status_code == 201, payment.text
        assert payment.json()["invoice"]["status"] == "paid"

        subscription = client.put(
            f"/api/v1/organizations/{org.id}/subscription",
            headers=headers,
            json={"plan": "pro", "status": "active"},
        )
        assert subscription.status_code == 200, subscription.text

def test_operational_api_rejects_cross_tenant_access():
    with TestClient(app) as client:
        tenant = TenantStore()
        accounting = AccountingStore()
        app.state.memberships = tenant
        app.state.accounting_store = accounting
        app.state.business_store = BusinessStore()

        owner = tenant.create_organization("Org One", 201)
        outsider = tenant.create_organization("Org Two", 202)
        token = issue_access_token(202)

        response = client.get(
            f"/api/v1/organizations/{owner.id}/accounts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_a_member"
        assert outsider.id != owner.id
