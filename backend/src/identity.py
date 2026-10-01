"""Resolving the caller behind a request.

TODO(auth): this module is a seam, not the final mechanism. Verified JWT
authentication does not exist yet, so the current user id is read from the
``X-User-Id`` request header and the organization is read from
:mod:`src.store`. Everything downstream of here -- membership, tenant scoping,
role ranking -- is real and enforced on every request; only the proof of
identity is provisional. When token verification lands it replaces
:func:`current_user_id` and nothing else in the request path changes.

What matters about the seam is the direction it fails in. A missing or
non-numeric ``X-User-Id`` raises ``not_authenticated``; it never falls back to a
default user. An unauthenticated caller must not reach a permission check as
somebody with no memberships and then be told "permission denied", because that
turns a missing token into a plausible-looking answer instead of an honest
failure, and it is the shape a client bug hides behind.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header

from .errors import ApiError, ErrorCode
from .store import InMemoryStore

USER_ID_HEADER = "X-User-Id"


class AuthenticationError(ApiError):
    """Raised when the request carries no usable caller identity, or a caller
    identity that has no standing in the requested organization.

    Carries the same codes and the same envelope as every other failure; the
    distinct type exists so the authentication paths can be read — and tested —
    on their own.
    """


@dataclass(frozen=True)
class Caller:
    """An authenticated user together with the organization they are acting in.

    ``role`` is the membership role resolved for this specific organization, not
    a global one: the same user may be an ``owner`` of one business and a
    ``viewer`` of another, and a check that used the higher of the two would
    leak the first business's ledger into the second.
    """

    user_id: int
    organization_id: int
    role: str


def current_user_id(
    x_user_id: str | None = Header(default=None, alias=USER_ID_HEADER),
) -> int:
    """Return the caller's user id, or raise a 401.

    Raises :class:`AuthenticationError` with ``not_authenticated`` rather than
    letting the exception escape as an opaque 500: a missing header has to be a
    401 carrying its stable code, which is what a client needs in order to tell
    "log in again" apart from "server broke".
    """
    if x_user_id is None or not x_user_id.strip():
        raise AuthenticationError(
            ErrorCode.NOT_AUTHENTICATED,
            f"the {USER_ID_HEADER} header is missing or blank",
            headers={"WWW-Authenticate": USER_ID_HEADER},
        )
    try:
        return int(x_user_id.strip())
    except ValueError as exc:
        raise AuthenticationError(
            ErrorCode.NOT_AUTHENTICATED,
            f"the {USER_ID_HEADER} header must be a user id",
        ) from exc


def resolve_caller(
    user_id: int, organization_id: int, memberships: InMemoryStore
) -> Caller:
    """Return the caller's role in ``organization_id``.

    Raises:
        AuthenticationError: ``organization_not_found`` if no such organization
            is registered, ``not_a_member`` if the caller has no membership in
            it. Both are checked before any ledger arithmetic runs.
    """
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