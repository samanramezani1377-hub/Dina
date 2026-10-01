"""Resolve the authenticated caller and tenant membership.

Production identity is the signed Bearer access token. The legacy X-User-Id
header is accepted only in the test environment so existing deterministic
fixtures remain usable; it is never an authentication mechanism in production.
"""
from __future__ import annotations
from dataclasses import dataclass
from fastapi import Request
from .auth import decode_access_token
from .config import get_settings
from .errors import ApiError, ErrorCode
from .store import InMemoryStore

USER_ID_HEADER = "X-User-Id"

class AuthenticationError(ApiError):
    """Authentication/tenant resolution failure using the standard envelope."""

@dataclass(frozen=True)
class Caller:
    user_id: int
    organization_id: int
    role: str

def current_user_id(request: Request) -> int:
    authorization = request.headers.get("Authorization", "")
    if authorization:
        scheme, separator, token = authorization.strip().partition(" ")
        if separator and scheme.lower() == "bearer" and token.strip():
            return decode_access_token(token.strip(), get_settings())
        raise AuthenticationError(ErrorCode.TOKEN_INVALID, "the Authorization header must use the Bearer scheme", status_code=401)
    if get_settings().is_test:
        value = request.headers.get(USER_ID_HEADER)
        if value and value.strip():
            try:
                return int(value.strip())
            except ValueError as exc:
                raise AuthenticationError(ErrorCode.NOT_AUTHENTICATED, "the X-User-Id header must be a user id") from exc
    raise AuthenticationError(
        ErrorCode.NOT_AUTHENTICATED,
        "an Authorization: Bearer <token> header is required",
        headers={"WWW-Authenticate": "Bearer"},
    )

def resolve_caller(user_id: int, organization_id: int, memberships: InMemoryStore) -> Caller:
    if organization_id not in memberships.organizations:
        raise AuthenticationError(
            ErrorCode.ORGANIZATION_NOT_FOUND,
            f"organization {organization_id} does not exist",
            {"organization_id": organization_id},
        )
    role = memberships.user_role(user_id, organization_id)
    if role is None:
        raise AuthenticationError(
            ErrorCode.NOT_A_MEMBER,
            f"user {user_id} is not a member of organization {organization_id}",
            {"user_id": user_id, "organization_id": organization_id},
        )
    return Caller(user_id=user_id, organization_id=organization_id, role=role)
