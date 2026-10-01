"""The error contract, asserted code by code.

Every failure the API can report is checked here for the same three things: the
envelope has exactly the keys ``code``, ``message`` and ``details``; the code is
the one the contract documents; and the status is the one the registry in
:mod:`src.errors` promises. A response that grew a fourth key, or that went back
to FastAPI's ``{"detail": ...}``, fails these tests rather than a client's
parser.

Two things are deliberately tested rather than assumed:

* **No code is documented without a path.** :data:`PRODUCED_CODES` accumulates
  the code every test below actually saw, and
  :func:`test_every_documented_code_is_produced` fails if the registry and that
  list have drifted apart. A code nobody can reach is a promise the API does not
  keep, and this is what catches one appearing in the registry.
* **A crash is not a contract.** :func:`test_an_unexpected_exception_never_leaks`
  drives a route that raises, and asserts the response carries a generic message
  and a correlation id while the traceback goes to the log.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from src.accounting_store import AccountingError, AccountingStore
from src.auth import UserDirectory, issue_access_token
from src.config import get_settings
from src.errors import (
    CORRELATION_ID_HEADER,
    ERROR_CODE_STATUS,
    ERROR_CODES,
    INTERNAL_ERROR_MESSAGE,
    ErrorCode,
    register_error_handlers,
)
from src.models import DRAFT, POSTED, JournalLine

from ledger_fixtures import (
    DAY_ONE,
    OTHER_ORGANIZATION_ID,
    ORGANIZATION_ID,
    OUTSIDER_USER_ID,
    VIEWER_USER_ID,
    as_accountant,
    force_unbalanced_posted_entry,
    line,
    other_org_account_id,
)

VALIDATE_URL = "/api/v1/accounting/journals/validate"

#: Every code a test in this file actually saw on the wire or in a raised
#: domain error. Compared against the registry by the two tests in the last
#: section, which is why they run after everything else in the file.
PRODUCED_CODES: set[str] = set()


def journal(**overrides) -> dict:
    """A journal body, with the keys a test cares about replaced."""
    body = {
        "organization_id": ORGANIZATION_ID,
        "document_no": "JV-ERR",
        "description": "error path",
        "lines": [
            {"account_id": 1, "debit": "100", "credit": "0"},
            {"account_id": 2, "debit": "0", "credit": "100"},
        ],
    }
    body.update(overrides)
    return body


def assert_envelope(
    response: Response,
    code: str,
    status_code: int | None = None,
    details: dict | None = None,
) -> dict:
    """Assert the exact envelope and return the error object.

    The key sets are asserted, not just the values: a handler that quietly added
    a ``traceback`` or a ``debug`` key would still pass a value-only assertion
    and still leak.
    """
    assert response.status_code == (
        ERROR_CODE_STATUS[code] if status_code is None else status_code
    ), response.text
    body = response.json()
    assert set(body) == {"error"}, f"the envelope must have one key: {body}"
    assert set(body["error"]) == {"code", "message", "details"}, body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert isinstance(body["error"]["details"], dict)
    if details is not None:
        assert body["error"]["details"] == details, body
    assert response.headers.get(CORRELATION_ID_HEADER), (
        "every error response is traceable through a correlation id"
    )
    PRODUCED_CODES.add(code)
    return body["error"]


def served_error(exc: Exception) -> Response:
    """Serve ``exc`` through the production handlers and return the response.

    Used for the domain codes whose endpoints do not exist yet: ``journal_-
    immutable``, the two reversal codes, the uniqueness conflicts and the two
    ``invalid_*`` codes are raised by the store, and this branch has no
    write endpoint that would surface them. Driving the raised exception
    through :func:`src.errors.register_error_handlers` is what proves the code
    and status reach the wire correctly, without a route invented just to be
    called by a test.
    """
    test_app = FastAPI()
    register_error_handlers(test_app)

    @test_app.get("/boom")
    def boom() -> None:
        raise exc

    return TestClient(test_app, raise_server_exceptions=False).get("/boom")


# ---------------------------------------------------------------------------
# Validation of the request itself
# ---------------------------------------------------------------------------


def test_a_malformed_body_is_a_validation_error(client) -> None:
    # `document_no` and `description` are required; sending a body without them
    # is a parse failure, not a domain failure, and must not be reported as one.
    error = assert_envelope(
        client.post(VALIDATE_URL, json={"organization_id": 1, "lines": []}),
        ErrorCode.VALIDATION_ERROR,
    )
    assert sorted(field["field"] for field in error["details"]["fields"]) == [
        "description",
        "document_no",
    ]


def test_a_non_numeric_amount_is_a_validation_error(client) -> None:
    error = assert_envelope(
        client.post(
            VALIDATE_URL,
            json=journal(
                lines=[{"account_id": 1, "debit": "not-a-number", "credit": "0"}]
            ),
        ),
        ErrorCode.VALIDATION_ERROR,
    )
    assert error["details"]["fields"][0]["field"] == "lines.0.debit"


def test_an_unknown_route_is_a_not_found_envelope(client) -> None:
    assert_envelope(
        client.get("/api/v1/accounting/nope"), ErrorCode.NOT_FOUND, status_code=404
    )


# ---------------------------------------------------------------------------
# Journal rules
# ---------------------------------------------------------------------------


def test_an_unbalanced_journal_reports_the_difference(client) -> None:
    assert_envelope(
        client.post(
            VALIDATE_URL,
            json=journal(
                lines=[
                    {"account_id": 1, "debit": "100", "credit": "0"},
                    {"account_id": 2, "debit": "0", "credit": "90"},
                ]
            ),
        ),
        ErrorCode.JOURNAL_NOT_BALANCED,
        details={
            "debit_total": "100",
            "credit_total": "90",
            "difference": "10",
        },
    )


def test_an_empty_journal_is_reported_as_empty(client) -> None:
    assert_envelope(
        client.post(VALIDATE_URL, json=journal(lines=[])),
        ErrorCode.JOURNAL_EMPTY,
        details={"line_count": 0},
    )


def test_a_line_with_both_sides_is_refused(client) -> None:
    assert_envelope(
        client.post(
            VALIDATE_URL,
            json=journal(
                lines=[
                    {"account_id": 1, "debit": "100", "credit": "100"},
                ]
            ),
        ),
        ErrorCode.LINE_MUST_HAVE_EXACTLY_ONE_SIDE,
    )


def test_a_line_with_neither_side_is_refused(client) -> None:
    assert_envelope(
        client.post(
            VALIDATE_URL,
            json=journal(
                lines=[
                    {"account_id": 1, "debit": "0", "credit": "0"},
                ]
            ),
        ),
        ErrorCode.LINE_MUST_HAVE_EXACTLY_ONE_SIDE,
    )


def test_a_negative_amount_is_refused(client) -> None:
    assert_envelope(
        client.post(
            VALIDATE_URL,
            json=journal(
                lines=[
                    {"account_id": 1, "debit": "-100", "credit": "0"},
                    {"account_id": 2, "debit": "0", "credit": "-100"},
                ]
            ),
        ),
        ErrorCode.AMOUNT_MUST_BE_NON_NEGATIVE,
    )


# ---------------------------------------------------------------------------
# Tenancy, membership and permission
# ---------------------------------------------------------------------------


def test_an_unknown_organization_is_reported_as_not_found(ledger_client, ledger_url) -> None:
    assert_envelope(
        ledger_client.get("/api/v1/organizations/4242/ledger", headers=as_accountant()),
        ErrorCode.ORGANIZATION_NOT_FOUND,
    )


def test_a_non_member_is_refused(ledger_client, ledger_url) -> None:
    # An authenticated outsider: 403, because what is missing is a membership
    # and telling them to log in again would be advice that cannot help.
    assert_envelope(
        ledger_client.get(ledger_url, headers=as_accountant(OUTSIDER_USER_ID)),
        ErrorCode.NOT_A_MEMBER,
    )


def test_a_viewer_is_refused(ledger_client, ledger_url) -> None:
    assert_envelope(
        ledger_client.get(ledger_url, headers=as_accountant(VIEWER_USER_ID)),
        ErrorCode.PERMISSION_DENIED,
    )


def test_a_request_with_no_identity_is_unauthenticated(ledger_client, ledger_url) -> None:
    assert_envelope(
        ledger_client.get(ledger_url), ErrorCode.NOT_AUTHENTICATED, status_code=401
    )


def test_a_non_numeric_identity_is_unauthenticated(ledger_client, ledger_url) -> None:
    assert_envelope(
        ledger_client.get(ledger_url, headers={"X-User-Id": "not-a-number"}),
        ErrorCode.NOT_AUTHENTICATED,
        status_code=401,
    )


def test_an_account_from_another_organization_is_not_found(
    ledger_client, ledger_url, accounting_store
) -> None:
    # 404, not 403: a cross-tenant id must not be distinguishable from an id that
    # does not exist, or the endpoint becomes a scanner for other tenants.
    assert_envelope(
        ledger_client.get(
            ledger_url,
            headers=as_accountant(),
            params={"account_id": other_org_account_id(accounting_store)},
        ),
        ErrorCode.ACCOUNT_NOT_FOUND,
    )


def test_an_unknown_entry_is_not_found(ledger_client, ledger_url) -> None:
    assert_envelope(
        ledger_client.get(ledger_url, headers=as_accountant(), params={"entry_id": 9999}),
        ErrorCode.JOURNAL_NOT_FOUND,
    )


# ---------------------------------------------------------------------------
# Domain codes raised by the store
# ---------------------------------------------------------------------------


HUNDRED = Decimal("100")
ZERO = Decimal("0")


def store_with_entries() -> tuple[AccountingStore, int, int]:
    """A store with two accounts, one posted entry and one draft.

    Returns ``(store, posted_id, draft_id)``: the reversal and immutability
    rules are about a *particular* entry's state, and reaching into the store to
    rediscover an id would make the test depend on id allocation order.
    """
    store = AccountingStore()
    store.add_organization(ORGANIZATION_ID)
    cash = store.add_account(ORGANIZATION_ID, "1100", "Cash", "asset")
    revenue = store.add_account(ORGANIZATION_ID, "4000", "Sales", "revenue")
    balanced = [
        JournalLine(account_id=cash.id, debit=HUNDRED, credit=ZERO),
        JournalLine(account_id=revenue.id, debit=ZERO, credit=HUNDRED),
    ]
    posted = store.add_entry(
        organization_id=ORGANIZATION_ID,
        document_no="JV-1",
        description="",
        entry_date=DAY_ONE,
        lines=balanced,
        status=POSTED,
    )
    draft = store.add_entry(
        organization_id=ORGANIZATION_ID,
        document_no="JV-2",
        description="",
        entry_date=DAY_ONE,
        lines=balanced,
        status=DRAFT,
    )
    return store, posted.id, draft.id


def test_a_reused_document_number_is_a_conflict() -> None:
    store, _, _ = store_with_entries()
    with pytest.raises(AccountingError) as raised:
        store.add_entry(
            organization_id=ORGANIZATION_ID,
            document_no="JV-1",
            description="a second entry with the same document number",
            entry_date=DAY_ONE,
            lines=[line(1, debit="1"), line(2, credit="1")],
        )
    assert raised.value.code == ErrorCode.DOCUMENT_NO_CONFLICT
    assert_envelope(served_error(raised.value), ErrorCode.DOCUMENT_NO_CONFLICT)


def test_a_reused_account_code_is_a_conflict() -> None:
    store, _, _ = store_with_entries()
    with pytest.raises(AccountingError) as raised:
        store.add_account(ORGANIZATION_ID, "1100", "Another cash", "asset")
    assert raised.value.code == ErrorCode.ACCOUNT_CODE_CONFLICT
    assert_envelope(served_error(raised.value), ErrorCode.ACCOUNT_CODE_CONFLICT)


def test_an_unknown_account_type_is_refused() -> None:
    store, _, _ = store_with_entries()
    with pytest.raises(AccountingError) as raised:
        store.add_account(ORGANIZATION_ID, "9000", "Crypto", "crypto")
    assert raised.value.code == ErrorCode.INVALID_ACCOUNT_TYPE
    assert_envelope(served_error(raised.value), ErrorCode.INVALID_ACCOUNT_TYPE)


def test_an_unknown_entry_status_is_refused() -> None:
    store, _, _ = store_with_entries()
    with pytest.raises(AccountingError) as raised:
        store.add_entry(
            organization_id=ORGANIZATION_ID,
            document_no="JV-3",
            description="",
            entry_date=DAY_ONE,
            lines=[line(1, debit="1")],
            status="banana",
        )
    assert raised.value.code == ErrorCode.INVALID_ENTRY_STATUS
    assert_envelope(served_error(raised.value), ErrorCode.INVALID_ENTRY_STATUS)


def test_a_posted_entry_cannot_be_posted_again() -> None:
    store, posted_id, _ = store_with_entries()
    with pytest.raises(AccountingError) as raised:
        store.post_entry(ORGANIZATION_ID, posted_id)
    assert raised.value.code == ErrorCode.JOURNAL_IMMUTABLE
    assert_envelope(served_error(raised.value), ErrorCode.JOURNAL_IMMUTABLE)


def test_a_draft_cannot_be_reversed() -> None:
    store, _, draft_id = store_with_entries()
    with pytest.raises(AccountingError) as raised:
        store.reverse_entry(ORGANIZATION_ID, draft_id, "REV-1", DAY_ONE)
    assert raised.value.code == ErrorCode.JOURNAL_NOT_REVERSIBLE
    assert_envelope(served_error(raised.value), ErrorCode.JOURNAL_NOT_REVERSIBLE)


def test_a_second_reversal_is_refused() -> None:
    store, posted_id, _ = store_with_entries()
    store.reverse_entry(ORGANIZATION_ID, posted_id, "REV-1", DAY_ONE)
    with pytest.raises(AccountingError) as raised:
        store.reverse_entry(ORGANIZATION_ID, posted_id, "REV-2", DAY_ONE)
    assert raised.value.code == ErrorCode.ENTRY_ALREADY_REVERSED
    assert_envelope(served_error(raised.value), ErrorCode.ENTRY_ALREADY_REVERSED)


def test_an_account_from_an_unknown_organization_is_not_found() -> None:
    store, _, _ = store_with_entries()
    with pytest.raises(AccountingError) as raised:
        store.get_account(OTHER_ORGANIZATION_ID, 1)
    assert raised.value.code == ErrorCode.ACCOUNT_NOT_FOUND
    assert_envelope(served_error(raised.value), ErrorCode.ACCOUNT_NOT_FOUND)


# ---------------------------------------------------------------------------
# Credentials and tokens
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_client() -> TestClient:
    """A booted app with an empty user directory."""
    from src.main import app

    with TestClient(app) as test_client:
        test_client.app.state.users = UserDirectory()
        yield test_client


STRONG_PASSWORD = "correct horse battery staple"


def test_registering_twice_is_a_conflict(auth_client) -> None:
    first = auth_client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": STRONG_PASSWORD},
    )
    assert first.status_code == 201
    assert_envelope(
        auth_client.post(
            "/api/v1/auth/register",
            json={"email": "OWNER@example.com", "password": STRONG_PASSWORD},
        ),
        ErrorCode.EMAIL_ALREADY_REGISTERED,
    )


def test_a_weak_password_is_a_validation_error(auth_client) -> None:
    assert_envelope(
        auth_client.post(
            "/api/v1/auth/register", json={"email": "owner@example.com", "password": "short"}
        ),
        ErrorCode.VALIDATION_ERROR,
    )


def test_a_malformed_email_is_a_validation_error(auth_client) -> None:
    assert_envelope(
        auth_client.post(
            "/api/v1/auth/register", json={"email": "not-an-email", "password": STRONG_PASSWORD}
        ),
        ErrorCode.VALIDATION_ERROR,
    )


def test_a_wrong_password_is_invalid_credentials(auth_client) -> None:
    auth_client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": STRONG_PASSWORD},
    )
    assert_envelope(
        auth_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "wrong password entirely"},
        ),
        ErrorCode.INVALID_CREDENTIALS,
        status_code=401,
    )


def test_an_unknown_email_is_also_invalid_credentials(auth_client) -> None:
    # Same code, deliberately: telling the two apart enumerates the user table.
    assert_envelope(
        auth_client.post(
            "/api/v1/auth/login",
            json={"email": "stranger@example.com", "password": STRONG_PASSWORD},
        ),
        ErrorCode.INVALID_CREDENTIALS,
        status_code=401,
    )


def test_a_token_verifies(auth_client) -> None:
    registered = auth_client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": STRONG_PASSWORD},
    )
    token = registered.json()["access_token"]
    me = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json() == {"user_id": 1, "email": "owner@example.com"}


def test_an_expired_token_says_so(auth_client) -> None:
    # Issued a minute in the past by the production issuer, so the expiry check is
    # exercised rather than a hand-edited payload with a broken signature.
    token = issue_access_token(
        1, get_settings(), expires_in=timedelta(minutes=-1)
    )
    assert_envelope(
        auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}),
        ErrorCode.TOKEN_EXPIRED,
        status_code=401,
    )


def test_a_garbage_token_is_invalid(auth_client) -> None:
    assert_envelope(
        auth_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"}
        ),
        ErrorCode.TOKEN_INVALID,
        status_code=401,
    )


def test_a_token_signed_with_another_key_is_invalid(auth_client) -> None:
    from src.config import Settings

    other = Settings(
        environment="test", secret_key="a-completely-different-key-of-32-chars"
    )
    token = issue_access_token(1, other)
    assert_envelope(
        auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}),
        ErrorCode.TOKEN_INVALID,
        status_code=401,
    )


def test_a_token_naming_another_algorithm_is_invalid(auth_client) -> None:
    """Algorithm confusion is refused even when the signature is genuine.

    A token whose header claims ``alg: none`` (or RS256) but which is correctly
    signed with the server key would be accepted by a verifier that trusts the
    header instead of the configuration. The check is therefore on the token
    *and* the configured algorithm together, and this test is what holds that
    line.
    """
    settings = get_settings()

    def segment(payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    claims = segment(
        {"sub": "1", "type": "access", "exp": int(time.time()) + 600}
    )
    header = segment({"alg": "none", "typ": "JWT"})
    signature = base64.urlsafe_b64encode(
        hmac.new(
            settings.require_secret_key().encode("utf-8"),
            f"{header}.{claims}".encode("ascii"),
            hashlib.sha256,
        ).digest()
    ).rstrip(b"=").decode("ascii")
    forged = f"{header}.{claims}.{signature}"

    assert_envelope(
        auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}),
        ErrorCode.TOKEN_INVALID,
        status_code=401,
    )


def test_a_missing_token_is_invalid(auth_client) -> None:
    assert_envelope(
        auth_client.get("/api/v1/auth/me"),
        ErrorCode.TOKEN_INVALID,
        status_code=401,
    )


def test_a_non_bearer_scheme_is_invalid(auth_client) -> None:
    assert_envelope(
        auth_client.get("/api/v1/auth/me", headers={"Authorization": "Basic dXNlcjpwdw=="}),
        ErrorCode.TOKEN_INVALID,
        status_code=401,
    )


# ---------------------------------------------------------------------------
# The unexpected
# ---------------------------------------------------------------------------


def crashing_app(message: str) -> FastAPI:
    """An app with one route that raises, and the production error handlers.

    ``raise_server_exceptions=False`` on the client below is the other half of
    the test: a crash must become a response, not an exception the test has to
    catch.
    """

    def explode() -> None:
        raise RuntimeError(message)

    test_app = FastAPI()
    register_error_handlers(test_app)
    test_app.add_api_route("/boom", explode, methods=["GET"])
    return test_app


def test_an_unexpected_exception_never_leaks(caplog) -> None:
    test_app = crashing_app(
        "connection string postgres://user:hunter2@db/dina refused"
    )

    with caplog.at_level(logging.ERROR, logger="dina.errors"):
        response = TestClient(test_app, raise_server_exceptions=False).get(
            "/boom", headers={"X-Correlation-Id": "req-4711"}
        )

    error = assert_envelope(response, ErrorCode.INTERNAL_ERROR, status_code=500)
    assert error["message"] == INTERNAL_ERROR_MESSAGE
    assert error["details"] == {"correlation_id": "req-4711"}
    assert response.headers[CORRELATION_ID_HEADER] == "req-4711"
    text = response.text
    for secret in ("hunter2", "connection string", "Traceback", "RuntimeError"):
        assert secret not in text, f"{secret!r} leaked into the response: {text}"
    # ...and the traceback did reach the log, keyed by the same id.
    assert "req-4711" in caplog.text
    assert "Traceback" in caplog.text
    assert "hunter2" in caplog.text


def test_a_crash_gets_a_correlation_id_when_the_caller_supplied_none(caplog) -> None:
    test_app = crashing_app("boom")

    with caplog.at_level(logging.ERROR, logger="dina.errors"):
        response = TestClient(test_app, raise_server_exceptions=False).get("/boom")

    error = assert_envelope(response, ErrorCode.INTERNAL_ERROR, status_code=500)
    assert error["details"]["correlation_id"] == response.headers[CORRELATION_ID_HEADER]
    assert error["details"]["correlation_id"] in caplog.text


# ---------------------------------------------------------------------------
# A code reported inside a successful response
# ---------------------------------------------------------------------------


def test_the_trial_balance_reports_an_imbalance_inside_a_200(
    trial_balance_client, accounting_store, trial_balance_url
) -> None:
    force_unbalanced_posted_entry(
        accounting_store, "JV-CORRUPT", DAY_ONE, [line(1, debit="0.05")]
    )
    response = trial_balance_client.get(trial_balance_url, headers=as_accountant())

    # The report is still delivered; the imbalance is carried in the same
    # `{code, message, details}` shape a client already knows how to read. A 200
    # that carries a code is still a code a client switches on, so it is
    # registered and documented like every other.
    assert response.status_code == 200
    error = response.json()["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == ErrorCode.TRIAL_BALANCE_UNBALANCED
    assert error["details"]["difference"] == "0.05"
    PRODUCED_CODES.add(ErrorCode.TRIAL_BALANCE_UNBALANCED)


# ---------------------------------------------------------------------------
# The registry itself
# ---------------------------------------------------------------------------


def test_every_documented_code_is_produced() -> None:
    """No code in the registry may be one nothing can return."""
    missing = ERROR_CODES - PRODUCED_CODES
    assert not missing, f"documented but unreachable: {sorted(missing)}"


def test_no_code_is_produced_that_is_not_documented() -> None:
    undocumented = PRODUCED_CODES - ERROR_CODES
    assert not undocumented, f"returned but undocumented: {sorted(undocumented)}"


def test_every_code_in_the_registry_is_documented_in_the_spec() -> None:
    """``docs/ERROR_CODES.md`` must list every code, and only real ones."""
    from pathlib import Path

    document = Path(__file__).resolve().parents[2] / "docs" / "ERROR_CODES.md"
    text = document.read_text(encoding="utf-8")
    missing = sorted(code for code in ERROR_CODES if code not in text)
    assert not missing, f"undocumented in docs/ERROR_CODES.md: {missing}"


def test_every_documented_status_is_a_real_http_status() -> None:
    assert all(100 <= value < 600 for value in ERROR_CODE_STATUS.values())
    assert len(set(ERROR_CODE_STATUS.values())) > 1
