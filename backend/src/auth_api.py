"""Registration, sign-in and "who am I".

Three routes, and they exist for a reason beyond convenience: they are the real
code paths for the authentication error codes — ``email_already_registered``,
``invalid_credentials``, ``token_expired`` and ``token_invalid``. A code that no
endpoint can produce is a promise the API cannot keep, so the endpoints that
produce them are part of this module rather than deferred to whenever login is
built.

Nothing here logs an email address together with a password, and no response
carries a password hash. The sign-in response holds the token and nothing else;
``/me`` proves a token works without ever returning the secret it verified.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .auth import UserDirectory, issue_access_token, token_user_id
from .config import Settings, get_settings
from .security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from .audit import AuditAction, record
from .rate_limit import enforce_auth_rate_limit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegistrationInput(BaseModel):
    """The body of ``POST /register``.

    Only the *upper* bound on the password is declared here. A multi-megabyte
    password has to be refused before it is buffered, which is a request-size
    concern and belongs on the model; the lower bound is the hash policy's
    business and stays in :func:`src.security.hash_password`, so the message a
    short password produces is the policy's message and not a second copy of it
    in a route.
    """

    email: str
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class CredentialsInput(BaseModel):
    """The body of ``POST /login``."""

    email: str
    password: str


def get_user_directory(request: Request) -> UserDirectory:
    """The process-wide user directory, attached during startup."""
    return request.app.state.users


@router.post("/register", status_code=201)
def register(
    payload: RegistrationInput,
    request: Request,
    users: UserDirectory = Depends(get_user_directory),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Create an account and sign the new user in.

    Returns the same token shape as :func:`login`, so a client does not need a
    second round trip after registering.
    """
    enforce_auth_rate_limit(request)
    try:
        user = users.register(payload.email, payload.password)
    except Exception:
        record(action=AuditAction.LOGIN_FAILED, entity="user", metadata={"operation": "register"})
        raise
    record(action=AuditAction.LOGIN_SUCCEEDED, entity="user", entity_id=user.user_id,
           user_id=user.user_id, metadata={"operation": "register"})
    return {
        "user_id": user.user_id,
        "email": user.email,
        "access_token": issue_access_token(user.user_id, settings),
        "token_type": "bearer",
    }


@router.post("/login")
def login(
    payload: CredentialsInput,
    request: Request,
    users: UserDirectory = Depends(get_user_directory),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Exchange credentials for an access token.

    A wrong email and a wrong password are the same ``invalid_credentials`` to
    the caller, and the comparison costs about the same either way — see
    :meth:`src.auth.UserDirectory.authenticate`.
    """
    enforce_auth_rate_limit(request)
    try:
        user = users.authenticate(payload.email, payload.password)
    except Exception:
        record(action=AuditAction.LOGIN_FAILED, entity="user", metadata={"operation": "login"})
        raise
    record(action=AuditAction.LOGIN_SUCCEEDED, entity="user", entity_id=user.user_id,
           user_id=user.user_id, metadata={"operation": "login"})
    return {
        "user_id": user.user_id,
        "email": user.email,
        "access_token": issue_access_token(user.user_id, settings),
        "token_type": "bearer",
    }


@router.get("/me")
def me(
    user_id: int = Depends(token_user_id), users: UserDirectory = Depends(get_user_directory)
) -> dict[str, object]:
    """Return the identity a bearer token proves.

    This endpoint is also the token path's failure mode: a token that does not
    verify answers ``token_invalid`` and one that has expired answers
    ``token_expired``, both through the standard envelope.
    """
    user = users.get(user_id)
    return {"user_id": user_id, "email": user.email if user is not None else None}


#: Re-exported so the request models' bounds are discoverable from one module.
__all__ = [
    "MIN_PASSWORD_LENGTH",
    "MAX_PASSWORD_LENGTH",
    "CredentialsInput",
    "RegistrationInput",
    "get_user_directory",
    "login",
    "me",
    "register",
    "router",
]