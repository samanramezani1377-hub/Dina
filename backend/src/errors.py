"""The API's error contract: one envelope, one enumerated set of codes.

Every failure the service reports to a client has the same shape::

    {"error": {"code": "journal_not_balanced", "message": "...", "details": {...}}}

**One shape for every failure.** Validation, domain rules, authentication,
membership, permissions, malformed request bodies and unexpected crashes all
leave through the same envelope, so a client parses one structure instead of
branching on which layer failed. The previous contract leaked ``str(exc)`` as
FastAPI's ``detail``, which made the Python exception text the public API: a
reworded error message was a breaking change, and an exception that escaped a
handler rendered a traceback into the response.

**Codes are the contract; messages are not.** A client switches on ``code``.
Messages are English prose for a human and may be reworded freely; a code must
never change meaning, must never be reused for a different condition, and must
never disappear. :data:`ERROR_CODE_STATUS` is the authoritative registry: the
status a code is served with, the one fact about a code that the server
guarantees alongside its name. :data:`ERROR_CODES` is the full enumerated set,
documented in ``docs/ERROR_CODES.md``.

**An unexpected crash is not a contract.** It is answered with
:data:`ErrorCode.INTERNAL_ERROR`, a generic message and the correlation id of
the failed request. The traceback goes to the log, keyed by that same id, and
never to the response: a traceback in an HTTP body leaks file paths, library
versions and data shapes to whoever triggered the crash, and it tells them
exactly what to try next.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("dina.errors")


class ErrorCode:
    """Every public error code, as string constants.

    Plain strings rather than an ``Enum`` so a code can be compared to a literal
    from a request body, a database row or an old client without a conversion in
    between, and so ``json.dumps`` of a code produces the wire value.
    """

    # -- request validation ------------------------------------------------
    VALIDATION_ERROR = "validation_error"

    # -- journal rules -----------------------------------------------------
    JOURNAL_EMPTY = "journal_empty"
    JOURNAL_NOT_BALANCED = "journal_not_balanced"
    LINE_MUST_HAVE_EXACTLY_ONE_SIDE = "line_must_have_exactly_one_side"
    AMOUNT_MUST_BE_NON_NEGATIVE = "amount_must_be_non_negative"
    JOURNAL_IMMUTABLE = "journal_immutable"
    JOURNAL_NOT_FOUND = "journal_not_found"
    JOURNAL_NOT_REVERSIBLE = "journal_not_reversible"
    ENTRY_ALREADY_REVERSED = "entry_already_reversed"
    INVALID_ENTRY_STATUS = "invalid_entry_status"

    # -- chart of accounts -------------------------------------------------
    ACCOUNT_NOT_FOUND = "account_not_found"
    ACCOUNT_CODE_CONFLICT = "account_code_conflict"
    INVALID_ACCOUNT_TYPE = "invalid_account_type"
    DOCUMENT_NO_CONFLICT = "document_no_conflict"

    # -- tenancy and access ------------------------------------------------
    ORGANIZATION_NOT_FOUND = "organization_not_found"
    NOT_A_MEMBER = "not_a_member"
    PERMISSION_DENIED = "permission_denied"
    NOT_AUTHENTICATED = "not_authenticated"
    NOT_FOUND = "not_found"

    # -- credentials and tokens -------------------------------------------
    INVALID_CREDENTIALS = "invalid_credentials"
    EMAIL_ALREADY_REGISTERED = "email_already_registered"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"

    #: The one code served *inside* a successful response. The trial balance
    #: reports that the posted entries do not agree in a 200 body rather than as
    #: a failed request, because the figures the operator needs are the payload;
    #: it is registered here anyway, since a client switches on it exactly like
    #: any other code and it must be documented like one.
    TRIAL_BALANCE_UNBALANCED = "trial_balance_unbalanced"

    # -- anything the server did not anticipate ---------------------------
    INTERNAL_ERROR = "internal_error"


#: The HTTP status each code is served with. The status is part of the
#: contract: a client that only reads the status (a proxy, a monitoring probe,
#: a retry policy) must still be able to tell "fix your request" from "log in
#: again" from "the server broke".
ERROR_CODE_STATUS: dict[str, int] = {
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.JOURNAL_EMPTY: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.JOURNAL_NOT_BALANCED: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.LINE_MUST_HAVE_EXACTLY_ONE_SIDE: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.AMOUNT_MUST_BE_NON_NEGATIVE: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.INVALID_ENTRY_STATUS: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.INVALID_ACCOUNT_TYPE: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.JOURNAL_IMMUTABLE: status.HTTP_409_CONFLICT,
    ErrorCode.JOURNAL_NOT_REVERSIBLE: status.HTTP_409_CONFLICT,
    ErrorCode.ENTRY_ALREADY_REVERSED: status.HTTP_409_CONFLICT,
    ErrorCode.DOCUMENT_NO_CONFLICT: status.HTTP_409_CONFLICT,
    ErrorCode.ACCOUNT_CODE_CONFLICT: status.HTTP_409_CONFLICT,
    ErrorCode.EMAIL_ALREADY_REGISTERED: status.HTTP_409_CONFLICT,
    ErrorCode.ACCOUNT_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.JOURNAL_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.ORGANIZATION_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.NOT_A_MEMBER: status.HTTP_403_FORBIDDEN,
    ErrorCode.PERMISSION_DENIED: status.HTTP_403_FORBIDDEN,
    ErrorCode.NOT_AUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.INVALID_CREDENTIALS: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.TOKEN_EXPIRED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.TOKEN_INVALID: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    # The only code served in a 200 body; see ErrorCode.TRIAL_BALANCE_UNBALANCED.
    ErrorCode.TRIAL_BALANCE_UNBALANCED: status.HTTP_200_OK,
}

#: Every code the service may ever return. New codes are added here first; a
#: code that is not in this set is a bug, and the test suite says so.
ERROR_CODES: frozenset[str] = frozenset(ERROR_CODE_STATUS)

#: Message returned for a crash. Deliberately vague: anything more specific
#: describes our internals to a caller who may be the one who caused the crash.
INTERNAL_ERROR_MESSAGE = "An unexpected error occurred."

#: Headers a caller may use to supply their own correlation id.
CORRELATION_ID_HEADERS = ("X-Correlation-Id", "X-Request-Id")

#: Header the correlation id is echoed back on, so a client that did not send
#: one can quote it in a support request.
CORRELATION_ID_HEADER = "X-Correlation-Id"


def status_for(code: str) -> int:
    """The status ``code`` is served with.

    Unknown codes are answered with 400 rather than 500. A code that is not
    registered means the server raised something it forgot to classify; calling
    it an internal error would claim the client's request caused a crash, while
    400 keeps the failure where it belongs — in our own bookkeeping — without
    ever putting an unclassified code on the wire.
    """
    return ERROR_CODE_STATUS.get(code, status.HTTP_400_BAD_REQUEST)


class ApiError(Exception):
    """A failure that already knows its code, its status and its details.

    Raised by any layer; converted into the envelope by the handler registered in
    :func:`register_error_handlers`. Carrying the code on the exception is what
    keeps a status-code decision out of the route that happens to hit the
    problem: the domain says *what* went wrong, the registry says how it is
    answered.
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
        status_code: int | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details or {})
        self.status_code = status_code if status_code is not None else status_for(code)
        self.headers = dict(headers or {})


def envelope(
    code: str, message: str, details: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Build the response body for a failure.

    ``details`` is always present, even when empty: a client that reads
    ``body["error"]["details"]["field"]`` must not have to branch on whether the
    key exists, and an absent key is indistinguishable from a value of ``None``.
    """
    return {"error": {"code": code, "message": message, "details": dict(details or {})}}


def correlation_id(request: Request | None) -> str:
    """The id that ties a response to its log lines.

    A caller-supplied ``X-Correlation-Id``/``X-Request-Id`` is honoured so a
    request can be followed across services; otherwise one is minted here. Either
    way the same id is logged with the traceback and returned to the caller, so
    "the server errored" and "here is the log line" meet in one identifier.
    """
    if request is not None:
        for header in CORRELATION_ID_HEADERS:
            value = request.headers.get(header)
            if value and value.strip():
                return value.strip()
    return uuid4().hex


def error_response(
    request: Request | None,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    status_code: int | None = None,
    headers: Mapping[str, str] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Render one envelope as a response, echoing the correlation id.

    The envelope itself stays exactly ``{code, message, details}`` for every
    failure, so ``details`` means "facts about this error" and nothing else. The
    correlation id travels in the response *header* on every error, and in
    ``details`` as well for :data:`ErrorCode.INTERNAL_ERROR`, where it is the
    one thing the caller needs in order to find the traceback.

    ``request_id`` exists because a caller that minted an id to log the traceback
    under must not then mint a second, different one for the header: the two
    would then be the only way to correlate a response with its own log line.
    """
    resolved_status = status_code if status_code is not None else status_for(code)
    request_id = request_id or correlation_id(request)
    response_headers = {CORRELATION_ID_HEADER: request_id, **dict(headers or {})}
    return JSONResponse(
        status_code=resolved_status, content=envelope(code, message, details), headers=response_headers
    )


def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Serve a failure that already carries a registered code."""
    if exc.code not in ERROR_CODE_STATUS:
        logger.warning(
            "error raised with unregistered code %r (%s)", exc.code, exc.message
        )
    return error_response(
        request,
        exc.code,
        exc.message,
        exc.details,
        status_code=exc.status_code,
        headers=exc.headers,
    )


def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Serve an ``HTTPException`` through the envelope.

    Only ``detail`` that is already a registered code is passed through as a
    code; anything else is prose about an HTTP failure and is mapped by status,
    so an unclassified detail can never reach a client as a pseudo-code.
    """
    detail = exc.detail
    if isinstance(detail, str) and detail in ERROR_CODE_STATUS:
        return error_response(request, detail, detail, status_code=exc.status_code)
    code = _code_for_status(exc.status_code)
    message = detail if isinstance(detail, str) and detail.strip() else code
    return error_response(request, code, message, status_code=exc.status_code)


def _code_for_status(status_code: int) -> str:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return ErrorCode.NOT_AUTHENTICATED
    if status_code == status.HTTP_403_FORBIDDEN:
        return ErrorCode.PERMISSION_DENIED
    if status_code == status.HTTP_404_NOT_FOUND:
        return ErrorCode.NOT_FOUND
    if status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ):
        return ErrorCode.VALIDATION_ERROR
    return ErrorCode.INTERNAL_ERROR


def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Serve a request-body or query-parameter parse failure.

    ``loc`` is trimmed of its leading ``body``/``query`` segment because the
    envelope already says the failure is a validation one; what a client needs is
    *which field*, so ``lines.0.debit`` rather than ``body.lines.0.debit``. The
    submitted value is deliberately not echoed: a rejected password or card
    number should not be reflected back into a log line.
    """
    fields = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ()) if part != "body"]
        fields.append(
            {
                "field": ".".join(location) or None,
                "message": error.get("msg", "invalid value"),
                "type": error.get("type", "value_error"),
            }
        )
    return error_response(
        request,
        ErrorCode.VALIDATION_ERROR,
        "the request body or query string is invalid",
        {"fields": fields},
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Serve a crash without leaking it.

    The traceback is logged with the correlation id and the response carries the
    id alone. Raising ``exc`` here would have Starlette's debug server re-raise
    into the test client instead of producing a response, and returning its text
    would publish our internals to whoever triggered it.
    """
    request_id = correlation_id(request)
    # exc_info is passed explicitly rather than left to logger.exception's
    # implicit sys.exc_info(): Starlette calls a handler for Exception from
    # outside the `except` block in some versions, where the implicit lookup finds
    # nothing and the operator gets "NoneType: None" instead of a traceback.
    logger.error(
        "unhandled exception on %s %s (correlation_id=%s)",
        request.method,
        request.url.path,
        request_id,
        exc_info=exc,
    )
    return error_response(
        request,
        ErrorCode.INTERNAL_ERROR,
        INTERNAL_ERROR_MESSAGE,
        {"correlation_id": request_id},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=request_id,
    )


def register_error_handlers(app: FastAPI) -> FastAPI:
    """Install every handler that renders :func:`envelope`.

    Order matters only in that the most specific class must be registered
    explicitly: Starlette resolves a handler by walking the raised exception's
    MRO, so a subclass handler wins over a base-class one. ``AccountingError``
    and ``AuthenticationError`` are subclasses of :class:`ApiError` and are named
    here so the mapping from their code to a status is visible in one place.
    """
    from .accounting_store import AccountingError
    from .identity import AuthenticationError

    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(AccountingError, _api_error_handler)
    app.add_exception_handler(AuthenticationError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)
    return app