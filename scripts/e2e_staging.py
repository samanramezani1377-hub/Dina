"""Real HTTP E2E against the persistent Dina staging backend."""
from __future__ import annotations
import os, sys, time
from datetime import date
from decimal import Decimal
import httpx

BASE = os.environ.get("DINA_API_BASE_URL", "https://dina-api.onrender.com").rstrip("/")
EMAIL = os.environ.get("DINA_E2E_EMAIL", "dina.test@example.com")
PASSWORD = os.environ.get("DINA_E2E_PASSWORD", "Dina-Test-2026!")

def check(response: httpx.Response, expected: int, label: str) -> dict:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}")
    return response.json() if response.text else {}

def main() -> None:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        check(client.get(f"{BASE}/health"), 200, "health")
        check(client.get(f"{BASE}/health/ready"), 200, "readiness")
        login = check(client.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}), 200, "login")
        token = login["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = check(client.get(f"{BASE}/api/v1/auth/me", headers=headers), 200, "me")
        orgs = check(client.get(f"{BASE}/api/v1/organizations", headers=headers), 200, "organizations")
        items = orgs.get("items", [])
        if not items:
            raise AssertionError("organizations: authenticated user has no organization")
        organization_id = int(items[0]["id"])
        accounts = check(client.get(f"{BASE}/api/v1/organizations/{organization_id}/accounts", headers=headers), 200, "accounts")
        account_items = accounts.get("items", [])
        if len(account_items) < 2:
            raise AssertionError("accounts: staging chart of accounts is incomplete")
        dashboard = check(client.get(f"{BASE}/api/v1/organizations/{organization_id}/trial-balance", headers=headers), 200, "dashboard/trial-balance")
        if "is_balanced" not in dashboard:
            raise AssertionError("dashboard: trial balance contract missing")
        code_to_id = {str(item["code"]): int(item["id"]) for item in account_items}
        issue_date = date.today().isoformat()
        journal = check(client.post(
            f"{BASE}/api/v1/organizations/{organization_id}/journals",
            headers=headers,
            json={
                "document_no": f"E2E-REAL-{int(time.time())}",
                "description": "E2E عملیات حسابداری واقعی",
                "entry_date": issue_date,
                "lines": [
                    {"account_id": code_to_id["1000"], "debit": "10.00", "credit": "0"},
                    {"account_id": code_to_id["4000"], "debit": "0", "credit": "10.00"},
                ],
            },
        ), 201, "create journal")
        entry_id = int(journal["id"])
        check(client.post(f"{BASE}/api/v1/organizations/{organization_id}/journals/{entry_id}/post", headers=headers), 200, "post journal")
        customer = check(client.post(
            f"{BASE}/api/v1/organizations/{organization_id}/customers",
            headers=headers,
            json={"name": f"E2E Customer {int(time.time())}"},
        ), 201, "create customer")
        sale = check(client.post(
            f"{BASE}/api/v1/organizations/{organization_id}/sales",
            headers=headers,
            json={
                "customer_id": int(customer["id"]),
                "invoice_no": f"E2E-SALE-{int(time.time())}",
                "issue_date": issue_date,
                "lines": [{
                    "description": "E2E sale",
                    "quantity": "1",
                    "unit_price": "10.00",
                    "discount": "0",
                    "tax": "0",
                }],
            },
        ), 201, "create sale draft")
        check(client.post(
            f"{BASE}/api/v1/organizations/{organization_id}/sales/{int(sale['id'])}/post",
            headers=headers,
            json={
                "receivable_or_payable_account_id": code_to_id["1200"],
                "revenue_or_inventory_account_id": code_to_id["4000"],
            },
        ), 200, "post sale")

        trial = check(client.get(
            f"{BASE}/api/v1/organizations/{organization_id}/reports/trial-balance",
            headers=headers,
            params={"as_of": issue_date},
        ), 200, "financial trial balance")
        if Decimal(trial["total_debit"]) != Decimal(trial["total_credit"]):
            raise AssertionError("financial trial balance is not balanced after posting a sale")
        sales_summary = check(client.get(
            f"{BASE}/api/v1/organizations/{organization_id}/reports/sales-summary",
            headers=headers,
            params={"date_from": issue_date, "date_to": issue_date},
        ), 200, "sales summary")
        if int(sales_summary["documents"]) < 1 or Decimal(sales_summary["total"]) < Decimal("10"):
            raise AssertionError("sales summary did not include the posted E2E sale")

        ledger = check(client.get(f"{BASE}/api/v1/organizations/{organization_id}/ledger", headers=headers), 200, "ledger")
        if Decimal(ledger["period_debit_total"]) <= Decimal("0"):
            raise AssertionError("ledger: expected a positive debit total")
        print("REAL E2E PASSED: health -> login -> organization -> journal -> post -> customer -> sale -> post -> trial balance -> sales report -> ledger")
        print("user_id=", me["user_id"], "organization_id=", organization_id)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"REAL E2E FAILED: {exc}", file=sys.stderr)
        raise
