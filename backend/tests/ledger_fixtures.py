"""Fixtures for the ledger tests.

The ledger is computed from persisted entries, so the tests need a store with
real accounts, real journal entries and real posting transitions -- the objects
the endpoint actually reads. Building them through :class:`AccountingStore`'s own
API (rather than reaching into its dictionaries) means a fixture cannot
manufacture a state the application would refuse to create, so a green test
here says something about the real code path.

Every fixture builds a fresh store, so no test can see another test's postings.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.accounting_store import AccountingStore
from src.main import app
from src.models import DRAFT, POSTED, JournalLine, Membership, Organization
from src.store import InMemoryStore

#: Two organizations, so tenant isolation is always testable. Org 1 is the one
#: under test; org 2 exists purely to be a different tenant.
ORGANIZATION_ID = 1
OTHER_ORGANIZATION_ID = 2

#: An accountant in org 1: the lowest role that may read a ledger.
ACCOUNTANT_USER_ID = 10
#: A viewer in org 1: below the accounting threshold.
VIEWER_USER_ID = 11
#: An accountant in org 2 and nothing else: a real user, but a stranger to org 1.
OUTSIDER_USER_ID = 12
#: No memberships at all.
STRANGER_USER_ID = 13

DAY_ONE = date(2026, 3, 1)
DAY_TWO = date(2026, 3, 2)
DAY_THREE = date(2026, 3, 3)
DAY_BEFORE = date(2026, 2, 28)
DAY_AFTER = date(2026, 3, 31)


def line(account_id: int, debit: str = "0", credit: str = "0") -> JournalLine:
    return JournalLine(
        account_id=account_id, debit=Decimal(debit), credit=Decimal(credit)
    )


@pytest.fixture
def accounting_store() -> AccountingStore:
    """A store with two organizations and a small chart of accounts each.

    Org 1 has a cash asset, a revenue account and an expense account; org 2 has
    its own cash account, so an id from one organization can never resolve
    inside the other.
    """
    store = AccountingStore()
    store.add_organization(ORGANIZATION_ID)
    store.add_organization(OTHER_ORGANIZATION_ID)
    store.add_account(ORGANIZATION_ID, "1100", "Cash", "asset")
    store.add_account(ORGANIZATION_ID, "4000", "Sales revenue", "revenue")
    store.add_account(ORGANIZATION_ID, "5000", "Rent expense", "expense")
    store.add_account(OTHER_ORGANIZATION_ID, "1100", "Cash", "asset")
    store.add_account(OTHER_ORGANIZATION_ID, "4000", "Sales revenue", "revenue")
    return store


@pytest.fixture
def memberships() -> InMemoryStore:
    """Memberships: an accountant and a viewer in org 1, an outsider in org 2."""
    return InMemoryStore(
        organizations={
            ORGANIZATION_ID: Organization(ORGANIZATION_ID, "Org One"),
            OTHER_ORGANIZATION_ID: Organization(OTHER_ORGANIZATION_ID, "Org Two"),
        },
        memberships=[
            Membership(ACCOUNTANT_USER_ID, ORGANIZATION_ID, "accountant"),
            Membership(ACCOUNTANT_USER_ID, OTHER_ORGANIZATION_ID, "owner"),
            Membership(VIEWER_USER_ID, ORGANIZATION_ID, "viewer"),
            Membership(OUTSIDER_USER_ID, OTHER_ORGANIZATION_ID, "accountant"),
        ],
    )


@pytest.fixture
def ledger_client(accounting_store, memberships) -> TestClient:
    """A booted app whose stores are the fixtures above."""
    with TestClient(app) as test_client:
        test_client.app.state.accounting_store = accounting_store
        test_client.app.state.memberships = memberships
        yield test_client


@pytest.fixture
def ledger_url() -> str:
    return f"/api/v1/organizations/{ORGANIZATION_ID}/ledger"


def as_accountant(user_id: int = ACCOUNTANT_USER_ID) -> dict[str, str]:
    return {"X-User-Id": str(user_id)}


def get_ledger(client: TestClient, url: str, **params) -> dict:
    """GET the ledger as an accountant. Tests pass ``params=`` for filters."""
    response = client.get(url, headers=as_accountant(), params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


def account_report(ledger: dict, account_id: int) -> dict:
    """The report block for one account, looked up by id."""
    for account in ledger["accounts"]:
        if account["account_id"] == account_id:
            return account
    raise AssertionError(f"account {account_id} is not in the ledger report")


def account_id(accounting_store: AccountingStore, code: str) -> int:
    """The id of ``code`` in org 1, resolved through the store's own lookup."""
    for account in accounting_store.list_accounts(ORGANIZATION_ID):
        if account.code == code:
            return account.id
    raise AssertionError(f"no account with code {code}")


def post_entry(
    accounting_store: AccountingStore,
    document_no: str,
    entry_date: date,
    lines: list[JournalLine],
    description: str = "",
) -> int:
    """Add an entry, post it, and return its id."""
    entry = accounting_store.add_entry(
        organization_id=ORGANIZATION_ID,
        document_no=document_no,
        description=description,
        entry_date=entry_date,
        lines=lines,
        status=DRAFT,
    )
    return accounting_store.post_entry(ORGANIZATION_ID, entry.id).id


def draft_entry(
    accounting_store: AccountingStore,
    document_no: str,
    entry_date: date,
    lines: list[JournalLine],
    description: str = "",
) -> int:
    """Add an entry and deliberately leave it a draft. Returns its id."""
    entry = accounting_store.add_entry(
        organization_id=ORGANIZATION_ID,
        document_no=document_no,
        description=description,
        entry_date=entry_date,
        lines=lines,
        status=DRAFT,
    )
    return entry.id


@pytest.fixture
def client_as(accounting_store):
    """Build a client whose caller holds ``role`` in org 1.

    A permission test needs to vary the caller's role, which the fixed
    ``ledger_client`` fixture cannot do. This yields a factory so each test
    states the role it is about.
    """
    from src.models import Membership, Organization

    def build(role: str) -> TestClient:
        memberships = InMemoryStore(
            organizations={ORGANIZATION_ID: Organization(ORGANIZATION_ID, "Org One")},
            memberships=[Membership(ACCOUNTANT_USER_ID, ORGANIZATION_ID, role)],
        )
        test_client = TestClient(app)
        test_client.__enter__()
        test_client.app.state.accounting_store = accounting_store
        test_client.app.state.memberships = memberships
        return test_client

    return build


def other_org_account_id(accounting_store: AccountingStore, code: str = "1100") -> int:
    """An account id belonging to org 2, resolved through the store's lookup."""
    for account in accounting_store.list_accounts(OTHER_ORGANIZATION_ID):
        if account.code == code:
            return account.id
    raise AssertionError(f"org 2 has no account with code {code}")


def post_other_org_entry(
    accounting_store: AccountingStore,
    document_no: str,
    entry_date: date,
    debit: str,
    description: str = "org two only",
) -> int:
    """Post a balanced entry in org 2 and return its id.

    Used by the tenant-isolation tests: it makes org 2 a real tenant with real
    postings, so "org 1's ledger is clean" cannot be satisfied by org 2 simply
    being empty.
    """
    entry = accounting_store.add_entry(
        organization_id=OTHER_ORGANIZATION_ID,
        document_no=document_no,
        description=description,
        entry_date=entry_date,
        lines=[
            line(other_org_account_id(accounting_store), debit=debit),
            line(other_org_account_id(accounting_store, "4000"), credit=debit),
        ],
        status=POSTED,
    )
    return entry.id
