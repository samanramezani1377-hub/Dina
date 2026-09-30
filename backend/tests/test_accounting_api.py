BALANCED_JOURNAL = {
    "organization_id": 1,
    "document_no": "JV-1",
    "description": "sale",
    "lines": [
        {"account_id": 1, "debit": "100", "credit": "0"},
        {"account_id": 2, "debit": "0", "credit": "100"},
    ],
}

UNBALANCED_JOURNAL = {
    "organization_id": 1,
    "document_no": "JV-2",
    "description": "bad",
    "lines": [
        {"account_id": 1, "debit": "100", "credit": "0"},
        {"account_id": 2, "debit": "0", "credit": "90"},
    ],
}


def test_balanced(client) -> None:
    r = client.post(
        "/api/v1/accounting/journals/validate", json=BALANCED_JOURNAL
    )
    assert r.status_code == 200 and r.json()["valid"] is True


def test_unbalanced(client) -> None:
    r = client.post(
        "/api/v1/accounting/journals/validate", json=UNBALANCED_JOURNAL
    )
    assert r.status_code == 422 and r.json()["detail"] == "journal_not_balanced"


def test_validator_runs_under_a_booted_lifespan(client) -> None:
    # Both cases above are served by a client that entered the TestClient
    # context manager, so the startup settings gate in src.main.lifespan ran.
    assert client.app.state.settings.is_test is True
