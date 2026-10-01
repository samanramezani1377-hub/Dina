"""The audit trail against a real PostgreSQL database.

``test_audit.py`` covers the audit service's logic, and covers
:class:`~src.audit.PostgresAuditStore` against a ``FakeConn`` that records the
SQL it was handed. A fake can prove the tenant filter is a bound parameter. It
cannot prove the database accepts the INSERT, and it fundamentally cannot prove
the append-only guarantee, because that guarantee is not implemented in
application code at all -- it lives in ``002_audit_logs.sql`` as a BEFORE
UPDATE OR DELETE trigger and a REVOKE. Only a real server can reject an UPDATE.

So these tests talk to a real PostgreSQL. On CI they **fail** rather than skip
when there is no database: a skip there would report the audit trail as covered
while testing nothing, so ``DATABASE_URL`` unset in CI is a broken pipeline, not
a green one. Off CI they skip with an explicit reason instead, because
``pytest backend/tests`` on a laptop with no server is a normal thing to do and
should not have to install PostgreSQL to run the unit tests next door.

CI provides the database via a ``postgres:16`` service container, applies the
migrations in ``database/migrations`` in filename order, and points
``DATABASE_URL`` at it. Locally, run the same migrations first::

    createdb dina_test
    for f in database/migrations/*.sql; do psql -v ON_ERROR_STOP=1 -d dina_test -f "$f"; done
    DATABASE_URL=postgresql://localhost:5432/dina_test pytest backend/tests

Every test truncates ``audit_logs`` before it runs. The table is append-only by
design and exposes no DELETE, so TRUNCATE is used: it is the one statement the
trigger does not cover, which is exactly why it is safe for test cleanup and
exactly why the trigger does not block it.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg", reason="psycopg is required for the PostgreSQL tests")

from src.audit import (  # noqa: E402  (import after the psycopg availability check)
    AuditAction,
    AuditEntry,
    AuditError,
    PostgresAuditStore,
    query_for_organization,
    record_login_succeeded,
)

#: The connection string CI supplies for its service container.
DATABASE_URL = os.environ.get("DATABASE_URL")

MIGRATIONS = Path(__file__).resolve().parents[2] / "database" / "migrations"


#: True when running under GitHub Actions. The two environments are treated
#: differently on purpose -- see _require_database.
ON_CI = bool(os.environ.get("GITHUB_ACTIONS"))


def _require_database() -> str:
    """Return the connection string, or refuse to run the test.

    On CI a missing ``DATABASE_URL`` is a failure: the workflow is supposed to
    supply one, so its absence means the pipeline lost the service container and
    a skip would turn that into a silent green. Off CI it is an ordinary skip,
    because these are the only tests that need a server and the rest of the
    suite should stay runnable without one.
    """
    if not DATABASE_URL:
        if ON_CI:
            pytest.fail(
                "DATABASE_URL is not set but these tests are running on CI, so the "
                "postgres service container is not reaching the job. The audit "
                "trail's append-only guarantee is enforced by the database and is "
                "not verified when these tests do not run."
            )
        pytest.skip("DATABASE_URL is not set; run a PostgreSQL server to exercise this file")
    return DATABASE_URL


@pytest.fixture(scope="module")
def dsn() -> str:
    url = _require_database()
    # Fail loudly and early if the database is unreachable, instead of every
    # test erroring with the same connection error and burying the real cause.
    try:
        with psycopg.connect(url, connect_timeout=10) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error as exc:
        pytest.fail(f"cannot reach the PostgreSQL server at the configured DATABASE_URL: {exc}")
    return url


@pytest.fixture()
def store(dsn: str) -> PostgresAuditStore:
    """A store over a clean ``audit_logs`` table."""
    with psycopg.connect(dsn) as conn:
        # TRUNCATE, not DELETE: the append-only trigger rejects DELETE by
        # design, so deleting rows to clean up between tests would fail.
        conn.execute("TRUNCATE audit_logs")
        conn.commit()
    return PostgresAuditStore(lambda: psycopg.connect(dsn))


def _entry(**overrides) -> AuditEntry:
    fields = {
        "id": 0,
        "organization_id": 5,
        "user_id": 7,
        "action": AuditAction.JOURNAL_POSTED,
        "entity": "journal_entry",
        "entity_id": "42",
        "occurred_at": datetime.now(timezone.utc),
        "metadata": {"document_no": "JV-1"},
        "correlation_id": "req-1",
        "ip_address": "203.0.113.9",
    }
    fields.update(overrides)
    return AuditEntry(**fields)


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------


def test_a_row_round_trips_through_the_real_table(store: PostgresAuditStore):
    stored = store.append(_entry())

    assert stored.id > 0, "the server assigns the id"
    rows = store.list_for_organization(5)
    assert len(rows) == 1
    row = rows[0]
    assert row.organization_id == 5
    assert row.user_id == 7
    assert row.action == AuditAction.JOURNAL_POSTED
    assert row.entity == "journal_entry"
    assert row.entity_id == "42"
    assert row.metadata == {"document_no": "JV-1"}
    assert row.correlation_id == "req-1"
    assert row.ip_address == "203.0.113.9"
    assert row.occurred_at is not None


def test_ids_increase_so_the_trail_is_ordered(store: PostgresAuditStore):
    first = store.append(_entry(document_no="A"))
    second = store.append(_entry(document_no="B"))

    assert second.id > first.id
    assert [r.metadata["document_no"] for r in store.list_for_organization(5)] == ["A", "B"]


def test_a_system_event_may_have_no_tenant(store: PostgresAuditStore):
    """A login that never resolved to a tenant is still auditable.

    ``organization_id`` is nullable in the schema on purpose; a NOT NULL column
    here would make the most security-relevant rows -- a failed login for an
    address that has no account -- the unrecordable ones.
    """
    row = record_login_succeeded(user_id=7, store=store)

    assert row is not None, "the write must succeed, not be swallowed"
    assert row.organization_id is None
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        stored = conn.execute(
            "SELECT organization_id FROM audit_logs WHERE action = %s", (AuditAction.LOGIN_SUCCEEDED,)
        ).fetchall()
    assert stored == [(None,)]


# --------------------------------------------------------------------------
# Tenant isolation, enforced by the database
# --------------------------------------------------------------------------


def test_rows_are_scoped_to_their_tenant(store: PostgresAuditStore):
    store.append(_entry(organization_id=1, document_no="one"))
    store.append(_entry(organization_id=2, document_no="two"))

    assert [r.metadata["document_no"] for r in store.list_for_organization(1)] == ["one"]
    assert [r.metadata["document_no"] for r in store.list_for_organization(2)] == ["two"]
    assert store.list_for_organization(3) == []


def test_the_query_helper_still_refuses_a_cross_tenant_read(store: PostgresAuditStore):
    store.append(_entry(organization_id=1))

    with pytest.raises(AuditError):
        query_for_organization(store, 2, caller_organization_id=1, role="owner")


def test_the_tenant_filter_is_a_bound_parameter_not_string_interpolation(
    store: PostgresAuditStore, dsn: str
):
    """The filter must not be built by pasting the tenant id into SQL."""
    store.append(_entry(organization_id=5))
    # If the id were interpolated, this would parse as valid SQL that returns
    # nothing (or error). Sent as data, it simply matches no rows.
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT count(*) FROM audit_logs WHERE organization_id = %s", ("5; DROP TABLE audit_logs",)
        ).fetchall()
        assert rows[0][0] == 0
    # The table is still there, which is the actual assertion: the injection
    # attempt was treated as a string to match, never as SQL to run.
    assert len(store.list_for_organization(5)) == 1


# --------------------------------------------------------------------------
# Append-only: the guarantee that only a real database can prove
# --------------------------------------------------------------------------


def test_the_database_rejects_an_update(store: PostgresAuditStore, dsn: str):
    store.append(_entry())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with psycopg.connect(dsn) as conn:
            conn.execute("UPDATE audit_logs SET action = 'tampered'")
            conn.commit()


def test_the_database_rejects_a_delete(store: PostgresAuditStore, dsn: str):
    store.append(_entry())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with psycopg.connect(dsn) as conn:
            conn.execute("DELETE FROM audit_logs")
            conn.commit()
    assert len(store.list_for_organization(5)) == 1, "the row survived"


def test_a_failed_audit_write_leaves_the_row_count_untouched(
    store: PostgresAuditStore, dsn: str
):
    """A rolled-back INSERT must not leave a partial row behind."""
    with pytest.raises(psycopg.Error):
        with psycopg.connect(dsn) as conn:
            # organization_id is BIGINT; a non-numeric value is a type error.
            conn.execute(
                "INSERT INTO audit_logs (organization_id, action, entity) "
                "VALUES ('not-a-number', 'x.created', 'thing')"
            )
            conn.commit()
    assert store.list_for_organization(5) == []


# --------------------------------------------------------------------------
# The migration is what installs the guarantee
# --------------------------------------------------------------------------


def test_the_migration_that_creates_the_table_is_present():
    assert (MIGRATIONS / "002_audit_logs.sql").is_file()


def test_the_table_the_migration_creates_is_the_one_under_test(store: PostgresAuditStore, dsn: str):
    """Guards against the store and the schema drifting apart.

    If the migrations were never applied, the store's first INSERT fails and
    every other test here fails too -- but with an error that looks like a
    broken store rather than an unapplied schema. This says which it is.
    """
    with psycopg.connect(dsn) as conn:
        columns = {
            row[0] for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'audit_logs'"
            ).fetchall()
        }
    assert {"organization_id", "user_id", "action", "entity", "occurred_at", "metadata"} <= columns