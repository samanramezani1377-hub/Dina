"""Audit trail tests: coverage, tenancy, redaction and failure isolation."""

import json
import logging

import pytest

from src import audit
from src.audit import (
    REDACTED,
    AuditAction,
    AuditError,
    AuditStore,
    InMemoryAuditStore,
    PostgresAuditStore,
    contains_secret_value,
    query_for_organization,
    record,
    redact,
)


#: Every one of these must never reach a row, whatever the caller does with it.
SECRETS = [
    "hunter2-super-secret-password",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NSJ9.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk",
    "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$RdescudvJCsgt3ub+b+dWRWJTmaaJObG",
    "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
    "Bearer sk-live-9f8a7b6c5d4e3f2a1b0c",
]

#: Values with a recognisable shape, so a pattern scan can catch them even when
#: the caller hides them under an innocuous key.
SHAPED_SECRETS = SECRETS[1:]


@pytest.fixture()
def store() -> InMemoryAuditStore:
    return InMemoryAuditStore()


# --------------------------------------------------------------------------
# One row per sensitive action, with the right action/entity/entity_id
# --------------------------------------------------------------------------


def test_login_success_records_exactly_one_row(store):
    entry = audit.record_login_succeeded(user_id=7, organization_id=3, email="a@b.co", store=store)
    assert entry is not None
    rows = store.rows
    assert len(rows) == 1
    assert rows[0].action == AuditAction.LOGIN_SUCCEEDED
    assert rows[0].entity == "user"
    assert rows[0].entity_id == "7"
    assert rows[0].organization_id == 3
    assert rows[0].user_id == 7
    assert rows[0].metadata["email"] == "a@b.co"
    assert rows[0].occurred_at is not None


def test_login_failure_records_exactly_one_row_with_reason_code(store):
    entry = audit.record_login_failed(
        email="ghost@example.com", reason_code="invalid_credentials", store=store
    )
    assert entry is not None
    rows = store.rows
    assert len(rows) == 1
    assert rows[0].action == AuditAction.LOGIN_FAILED
    assert rows[0].metadata["reason_code"] == "invalid_credentials"
    # A failed login for an unknown email belongs to no tenant.
    assert rows[0].organization_id is None


def test_logout_records_exactly_one_row(store):
    audit.record_logout(user_id=7, organization_id=3, store=store)
    assert [r.action for r in store.rows] == [AuditAction.LOGOUT]


def test_organization_creation_records_exactly_one_row(store):
    audit.record_organization_created(organization_id=11, user_id=7, name="Dinco", store=store)
    rows = store.rows
    assert len(rows) == 1
    assert rows[0].action == AuditAction.ORGANIZATION_CREATED
    assert rows[0].entity == "organization"
    assert rows[0].entity_id == "11"


def test_membership_add_and_remove_each_record_one_row(store):
    audit.record_membership_added(
        organization_id=11, user_id=7, member_user_id=8, role="accountant", store=store
    )
    audit.record_membership_removed(
        organization_id=11, user_id=7, member_user_id=8, role="accountant", store=store
    )
    rows = store.rows
    assert len(rows) == 2
    assert [r.action for r in rows] == [
        AuditAction.MEMBERSHIP_ADDED,
        AuditAction.MEMBERSHIP_REMOVED,
    ]
    for row in rows:
        assert row.entity == "membership"
        assert row.entity_id == "11:8"
        assert row.metadata["role"] == "accountant"


def test_account_creation_records_exactly_one_row(store):
    audit.record_account_created(
        organization_id=11, user_id=7, account_id=42, code="1000", account_type="asset", store=store
    )
    rows = store.rows
    assert len(rows) == 1
    assert rows[0].action == AuditAction.ACCOUNT_CREATED
    assert rows[0].entity == "account"
    assert rows[0].entity_id == "42"
    assert rows[0].metadata == {"code": "1000", "account_type": "asset"}


def test_journal_lifecycle_records_one_row_per_step(store):
    audit.record_journal_created(
        organization_id=11, user_id=7, journal_id=100, document_no="JV-1", line_count=2, store=store
    )
    audit.record_journal_posted(
        organization_id=11, user_id=7, journal_id=100, document_no="JV-1", store=store
    )
    audit.record_journal_reversed(
        organization_id=11, user_id=7, journal_id=100, reversal_id=101, document_no="JV-1", store=store
    )
    audit.record_journal_corrected(
        organization_id=11, user_id=7, journal_id=100, correction_id=102, document_no="JV-1", store=store
    )
    rows = store.rows
    assert len(rows) == 4
    assert [r.action for r in rows] == [
        AuditAction.JOURNAL_CREATED,
        AuditAction.JOURNAL_POSTED,
        AuditAction.JOURNAL_REVERSED,
        AuditAction.JOURNAL_CORRECTED,
    ]
    assert all(r.entity == "journal_entry" for r in rows)
    assert all(r.entity_id == "100" for r in rows)
    assert rows[0].metadata["line_count"] == 2
    assert rows[2].metadata["reversal_id"] == 101
    assert rows[3].metadata["correction_id"] == 102


def test_payment_and_subscription_helpers_record_one_row_each(store):
    audit.record_payment_recorded(
        organization_id=11, user_id=7, payment_id=500, amount="1250.75", currency="IRR", store=store
    )
    audit.record_subscription_changed(
        organization_id=11,
        user_id=7,
        subscription_id=900,
        change="upgrade",
        status="active",
        store=store,
    )
    rows = store.rows
    assert len(rows) == 2
    assert rows[0].action == AuditAction.PAYMENT_RECORDED
    assert rows[0].entity == "payment"
    assert rows[0].entity_id == "500"
    assert rows[0].metadata["amount"] == "1250.75"
    assert rows[1].action == AuditAction.SUBSCRIPTION_CHANGED
    assert rows[1].entity == "subscription"
    assert rows[1].entity_id == "900"


def test_entity_id_accepts_uuid_like_values(store):
    entry = record(
        action=AuditAction.ACCOUNT_CREATED,
        entity="account",
        entity_id="3f2b8c1e-0d9a-4f7b-8c2d-1a2b3c4d5e6f",
        organization_id=11,
        store=store,
    )
    assert entry.entity_id == "3f2b8c1e-0d9a-4f7b-8c2d-1a2b3c4d5e6f"


# --------------------------------------------------------------------------
# Redaction: a caller cannot accidentally persist a secret
# --------------------------------------------------------------------------


def test_sensitive_keys_are_redacted():
    redacted = redact(
        {
            "password": "hunter2-super-secret-password",
            "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$RdescudvJCsgt3ub+b+dWRWJTmaaJObG",
            "user_password_hash": "abc",
            "access_token": "abc",
            "refreshToken": "abc",
            "Authorization": "Bearer sk-live-9f8a7b6c5d4e3f2a1b0c",
            "api_key": "abc",
            "apiSecret": "abc",
            "client_secret": "abc",
            "private_key": "abc",
            "session_id": "abc",
            "Cookie": "abc",
            "signature": "abc",
            "otp": "123456",
        }
    )
    for key, value in redacted.items():
        assert value == REDACTED, key


def test_non_sensitive_keys_survive():
    redacted = redact({"organization_id": 11, "role": "owner", "document_no": "JV-1", "line_count": 2})
    assert redacted == {
        "organization_id": 11,
        "role": "owner",
        "document_no": "JV-1",
        "line_count": 2,
    }


def test_nested_structures_are_redacted():
    redacted = redact(
        {
            "request": {"headers": {"authorization": "Bearer abc"}, "user": {"email": "a@b.co"}},
            "items": [{"password": "p"}, "fine"],
        }
    )
    assert redacted["request"]["headers"]["authorization"] == REDACTED
    assert redacted["request"]["user"]["email"] == "a@b.co"
    assert redacted["items"][0]["password"] == REDACTED
    assert redacted["items"][1] == "fine"


def test_secret_shaped_values_are_redacted_even_under_innocuous_keys():
    for secret in SHAPED_SECRETS:
        redacted = redact({"note": f"login attempt with {secret} attached"})
        assert secret not in json.dumps(redacted), secret
        assert not contains_secret_value(json.dumps(redacted)), secret


def test_login_helpers_never_persist_credentials(store):
    audit.record_login_succeeded(
        user_id=7,
        organization_id=3,
        email="a@b.co",
        store=store,
        metadata={"password": SECRETS[0], "token": SECRETS[1], "note": f"raw {SECRETS[2]}"},
    )
    serialised = json.dumps(store.rows[0].metadata)
    for secret in SECRETS:
        assert secret not in serialised, secret


def test_correlation_id_and_ip_are_redacted(store):
    entry = record(
        action=AuditAction.LOGIN_FAILED,
        entity="user",
        organization_id=3,
        correlation_id="Bearer sk-live-9f8a7b6c5d4e3f2a1b0c",
        ip_address="password=hunter2-super-secret-password",
        store=store,
    )
    assert entry.correlation_id == REDACTED
    assert entry.ip_address == REDACTED


def test_large_metadata_is_truncated_but_still_usable(store):
    """A payload over the size limit must keep the keys that fit.

    The previous implementation truncated the *serialised* JSON, which can
    never be parsed back, so every oversized payload lost everything to
    ``{"metadata_unavailable": True}``.
    """
    payload = {f"line_{i:04d}": "x" * 200 for i in range(200)}
    entry = record(
        action=AuditAction.JOURNAL_CREATED,
        entity="journal_entry",
        organization_id=11,
        metadata=payload,
        store=store,
    )
    serialised = json.dumps(entry.metadata, default=str)
    assert len(serialised) <= audit.MAX_METADATA_CHARS
    assert entry.metadata, "an oversized payload must not be discarded entirely"
    assert entry.metadata["metadata_truncated"] is True
    # Every retained value is still readable, i.e. the payload round-trips.
    assert entry.metadata["line_0000"] == "x" * 200
    assert all(
        isinstance(v, str) for k, v in entry.metadata.items() if k != "metadata_truncated"
    )


def test_a_single_oversized_value_is_capped_before_serialisation(store):
    entry = record(
        action=AuditAction.ORGANIZATION_CREATED,
        entity="organization",
        organization_id=11,
        metadata={"description": "y" * 50_000, "name": "Dinco"},
        store=store,
    )
    assert entry.metadata["name"] == "Dinco"
    assert entry.metadata["description"].endswith("…[truncated]")
    assert len(entry.metadata["description"]) <= audit.MAX_METADATA_STRING_CHARS + 32


def test_backstop_drops_metadata_when_a_secret_survives_the_tree_walk(monkeypatch, store):
    def leaky(value, *, _depth=0):
        # Simulate a future value type that leaks a secret past the tree walk.
        return {"leaked": SECRETS[3]}

    monkeypatch.setattr(audit, "redact", leaky)
    entry = audit.record_login_succeeded(
        user_id=7, organization_id=3, metadata={"anything": 1}, store=store
    )
    assert entry.metadata == {"metadata_dropped": True, "redaction_applied": True}
    assert not contains_secret_value(json.dumps(entry.metadata))


def test_deeply_nested_metadata_is_bounded(store):
    payload = current = {}
    for _ in range(40):
        current["next"] = {}
        current = current["next"]
    current["password"] = "hunter2-super-secret-password"
    entry = record(
        action=AuditAction.ORGANIZATION_CREATED,
        entity="organization",
        organization_id=11,
        metadata=payload,
        store=store,
    )
    assert SECRETS[0] not in json.dumps(entry.metadata)


def test_no_audit_row_anywhere_contains_a_secret(store):
    audit.record_login_succeeded(user_id=1, organization_id=1, email="a@b.co", store=store)
    audit.record_login_failed(email="b@b.co", reason_code="invalid_credentials", store=store)
    audit.record_organization_created(organization_id=1, user_id=1, name="A", store=store)
    audit.record_membership_added(organization_id=1, user_id=1, member_user_id=2, role="viewer", store=store)
    audit.record_account_created(
        organization_id=1, user_id=1, account_id=1, code="1", account_type="asset", store=store
    )
    audit.record_journal_posted(
        organization_id=1, user_id=1, journal_id=1, document_no="JV-1", store=store
    )
    for row in store.rows:
        blob = json.dumps(row.to_dict(), default=str)
        for secret in SECRETS:
            assert secret not in blob, (row.action, secret)
        assert not contains_secret_value(blob), row.action


# --------------------------------------------------------------------------
# Tenancy
# --------------------------------------------------------------------------


def test_cross_tenant_read_is_impossible(store):
    audit.record_account_created(
        organization_id=1, user_id=7, account_id=1, code="1", account_type="asset", store=store
    )
    audit.record_account_created(
        organization_id=2, user_id=9, account_id=2, code="1", account_type="asset", store=store
    )
    org_one = query_for_organization(store, 1, caller_organization_id=1, role="owner")
    assert [r.entity_id for r in org_one] == ["1"]
    assert all(r.organization_id == 1 for r in org_one)
    # A caller authorized for org 1 asking for org 2 is refused, not merely
    # empty, even though "owner" is a role that may read org 2's trail.
    with pytest.raises(AuditError):
        query_for_organization(store, 2, caller_organization_id=1, role="owner")


def test_cross_tenant_read_raises_before_touching_the_store():
    class ExplodingStore(AuditStore):
        def append(self, entry):  # pragma: no cover
            raise AssertionError("append must not be called")

        def list_for_organization(self, organization_id):
            raise AssertionError("a refused read must not query the store")

        def list_for_action(self, action):  # pragma: no cover
            raise AssertionError("a refused read must not query the store")

    with pytest.raises(AuditError):
        query_for_organization(
            ExplodingStore(), 2, caller_organization_id=1, role="owner"
        )


def test_query_returns_nothing_for_an_authorized_organization_without_rows(store):
    audit.record_organization_created(organization_id=1, user_id=7, name="A", store=store)
    assert query_for_organization(store, 999, caller_organization_id=999, role="owner") == []


@pytest.mark.parametrize("role", ["accountant", "sales", "warehouse", "viewer", "unknown", None])
def test_unauthorized_roles_cannot_read_the_audit_trail(store, role):
    audit.record_organization_created(organization_id=1, user_id=7, name="A", store=store)
    with pytest.raises(AuditError):
        query_for_organization(store, 1, caller_organization_id=1, role=role)


def test_query_requires_an_organization_id(store):
    with pytest.raises(AuditError):
        query_for_organization(store, None, caller_organization_id=1, role="owner")


def test_query_requires_an_explicit_caller_organization_id(store):
    audit.record_organization_created(organization_id=1, user_id=7, name="A", store=store)
    with pytest.raises(TypeError):
        query_for_organization(store, 1, role="owner")
    with pytest.raises(AuditError):
        query_for_organization(store, 1, caller_organization_id=None, role="owner")


@pytest.mark.parametrize("role", sorted(audit.AUDIT_READ_ROLES))
def test_authorized_roles_can_read_their_organization(store, role):
    audit.record_organization_created(organization_id=1, user_id=7, name="A", store=store)
    rows = query_for_organization(store, 1, caller_organization_id=1, role=role)
    assert [r.action for r in rows] == [AuditAction.ORGANIZATION_CREATED]


def test_query_can_filter_by_action_and_actor(store):
    audit.record_journal_posted(organization_id=1, user_id=7, journal_id=1, document_no="A", store=store)
    audit.record_journal_posted(organization_id=1, user_id=8, journal_id=2, document_no="B", store=store)
    by_action = query_for_organization(
        store, 1, caller_organization_id=1, role="owner", action=AuditAction.JOURNAL_POSTED
    )
    assert len(by_action) == 2
    by_actor = query_for_organization(store, 1, caller_organization_id=1, role="owner", user_id=8)
    assert [r.entity_id for r in by_actor] == ["2"]


def test_postgres_store_filters_by_organization_with_a_parameterised_query():
    captured = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return [
                (1, 5, 7, "organization.created", "organization", "5", None, {}, None, None)
            ]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            captured["closed"] = True

    store = PostgresAuditStore(lambda: FakeConn())
    rows = store.list_for_organization(5)
    assert captured["params"] == (5,)
    # Tenant scoping must be a bound parameter, never string interpolation.
    assert "organization_id = %s" in captured["sql"]
    assert "5" not in captured["sql"]
    assert rows[0].organization_id == 5
    assert captured["closed"] is True


# --------------------------------------------------------------------------
# Append-only
# --------------------------------------------------------------------------


def test_stores_expose_no_update_or_delete_path():
    for store in (InMemoryAuditStore(), PostgresAuditStore(lambda: None)):
        for forbidden in ("update", "delete", "truncate", "purge", "remove", "clear"):
            assert not hasattr(store, forbidden), forbidden
            assert not hasattr(AuditStore, forbidden), forbidden


def test_migration_declares_append_only_enforcement():
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[2] / "database" / "migrations" / "002_audit_logs.sql"
    ).read_text()
    assert "REVOKE UPDATE, DELETE" in sql
    assert "BEFORE UPDATE OR DELETE ON audit_logs" in sql
    assert "append-only" in sql
    for column in (
        "organization_id",
        "user_id",
        "action",
        "entity",
        "entity_id",
        "occurred_at",
        "metadata JSONB",
        "correlation_id",
        "ip_address",
    ):
        assert column in sql, column
    for index in (
        "idx_audit_logs_org",
        "idx_audit_logs_user",
        "idx_audit_logs_action",
        "idx_audit_logs_occurred_at",
    ):
        assert index in sql, index


# --------------------------------------------------------------------------
# Failure isolation: an audit failure must not break the business operation
# --------------------------------------------------------------------------


class BrokenStore(AuditStore):
    def append(self, entry):
        raise RuntimeError("audit database is down")

    def list_for_organization(self, organization_id):
        raise RuntimeError("audit database is down")

    def list_for_action(self, action):
        raise RuntimeError("audit database is down")


def test_audit_failure_does_not_propagate(caplog):
    with caplog.at_level(logging.ERROR, logger="dina.audit"):
        result = audit.record_login_succeeded(user_id=7, organization_id=3, store=BrokenStore())
    assert result is None
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    assert "audit write failed" in caplog.text


def test_audit_failure_leaves_the_business_operation_intact(caplog):
    def business_operation():
        audit.record_journal_posted(
            organization_id=3, user_id=7, journal_id=1, document_no="JV-1", store=BrokenStore()
        )
        return {"status": "posted", "journal_id": 1}

    with caplog.at_level(logging.ERROR, logger="dina.audit"):
        assert business_operation()["status"] == "posted"


def test_record_returns_the_stored_entry(store):
    entry = audit.record_login_succeeded(user_id=7, organization_id=3, store=store)
    assert entry.id == 1
    assert store.rows[0] is entry


# --------------------------------------------------------------------------
# Wiring into the live call sites
# --------------------------------------------------------------------------


def test_journal_validate_endpoint_audits_accepted_and_rejected_attempts():
    from fastapi.testclient import TestClient

    from src import audit as audit_module
    from src.main import app

    before = len(audit_module.DEFAULT_STORE.rows)
    client = TestClient(app)

    ok = client.post(
        "/api/v1/accounting/journals/validate",
        json={
            "organization_id": 1,
            "document_no": "JV-OK",
            "description": "sale",
            "lines": [
                {"account_id": 1, "debit": "100", "credit": "0"},
                {"account_id": 2, "debit": "0", "credit": "100"},
            ],
        },
        headers={"x-request-id": "req-1"},
    )
    assert ok.status_code == 200
    bad = client.post(
        "/api/v1/accounting/journals/validate",
        json={
            "organization_id": 1,
            "document_no": "JV-BAD",
            "description": "bad",
            "lines": [
                {"account_id": 1, "debit": "100", "credit": "0"},
                {"account_id": 2, "debit": "0", "credit": "90"},
            ],
        },
    )
    assert bad.status_code == 422

    rows = audit_module.DEFAULT_STORE.rows[before:]
    assert len(rows) == 2
    assert [r.metadata["outcome"] for r in rows] == ["validated", "rejected"]
    assert [r.metadata["document_no"] for r in rows] == ["JV-OK", "JV-BAD"]
    assert rows[1].metadata["reason_code"] == "journal_not_balanced"
    assert rows[0].correlation_id == "req-1"
    assert rows[0].ip_address == "testclient"
    for row in rows:
        assert not contains_secret_value(json.dumps(row.to_dict(), default=str))


def test_anonymous_caller_cannot_forge_an_audit_row_into_a_tenant():
    """The body organization_id is a claim, not an authorization.

    The route has no authentication, so the audited row must carry no tenant
    at all; the claimed id is only kept as a non-tenant detail.
    """
    from fastapi.testclient import TestClient

    from src import audit as audit_module
    from src.main import app

    before = len(audit_module.DEFAULT_STORE.rows)
    client = TestClient(app)
    response = client.post(
        "/api/v1/accounting/journals/validate",
        json={
            "organization_id": 999,
            "document_no": "JV-FORGED",
            "description": "forged",
            "lines": [
                {"account_id": 1, "debit": "100", "credit": "0"},
                {"account_id": 2, "debit": "0", "credit": "100"},
            ],
        },
    )
    assert response.status_code == 200
    rows = audit_module.DEFAULT_STORE.rows[before:]
    assert len(rows) == 1
    assert rows[0].organization_id is None
    assert rows[0].metadata["claimed_organization_id"] == 999
    # Nothing lands in the forged tenant's trail.
    assert audit_module.DEFAULT_STORE.list_for_organization(999) == []


def test_helpers_reject_misspelled_arguments(store):
    """Silently swallowing a typo means an audit row missing its detail."""
    with pytest.raises(TypeError):
        audit.record_journal_posted(
            organization_id=1, user_id=1, journal_id=1, document_no="JV-1", store_typo=store
        )
    with pytest.raises(TypeError):
        audit.record_logout(user_id=1, organization_id=1, metadata={"reason": "user"}, stroe=store)
    assert store.rows == []


def test_logout_records_the_metadata_it_was_given(store):
    audit.record_logout(
        user_id=7, organization_id=3, metadata={"reason": "user_request"}, store=store
    )
    assert store.rows[0].metadata == {"reason": "user_request"}
    assert store.rows[0].organization_id == 3
    assert store.rows[0].user_id == 7


def test_default_store_is_bounded_and_non_durable():
    assert audit.DEFAULT_STORE_MAX_ROWS > 0
    assert isinstance(audit.DEFAULT_STORE, InMemoryAuditStore)
    bounded = InMemoryAuditStore(max_rows=2)
    for i in range(2):
        bounded.append(
            audit.AuditEntry(
                id=i,
                organization_id=1,
                user_id=1,
                action=AuditAction.LOGOUT,
                entity="user",
                entity_id="1",
                occurred_at=audit.datetime.now(audit.timezone.utc),
            )
        )
    # The bound refuses new rows; it never drops existing ones, because that
    # would be a delete path.
    with pytest.raises(RuntimeError):
        bounded.append(bounded.rows[-1])
    assert len(bounded.rows) == 2
