"""Credentials and access tokens, and the codes a client sees when they fail.

The bead this module answers for requires every documented error code to be
produced by a real code path, which rules out the tempting shortcut of writing
``invalid_credentials``, ``token_expired``, ``token_invalid`` and
``email_already_registered`` into a table and raising them from nowhere. Each of
those four exists here because a real caller can hit it, and
``backend/tests/test_errors.py`` drives each one through a real endpoint.

**A token is signed, not encoded.** A JWT-shaped token is only useful if the
server checks a signature it did not receive from the client; an unsigned token
is a base64 blob the client can rewrite to claim any user id, including an
administrator. The signature is HMAC-SHA256 over ``base64url(header).base64url(
payload)`` using :meth:`src.config.Settings.require_secret_key`, and it is
compared with :func:`hmac.compare_digest`, which does not leak how many
leading bytes matched through timing.

**Failure is closed and specific.** A token that does not verify is
``token_invalid``; one that verifies but whose ``exp`` has passed is
``token_expired``. The two are separate codes because they are separate
instructions for the client: the first means "the token is not ours, throw it
away", the second means "it was ours, get a new one". Collapsing them into one
code would leave the client guessing which action to take. An *expired* token
is still checked for a valid signature first, so an attacker cannot mint a
request that says "expired" and watch the server accept the claim that it
verified.

**No algorithm confusion.** The header is compared against the configured
algorithm rather than read out of the token, and only the configured HMAC is
ever constructed. A token that asks for ``alg: none`` or for RS256 is rejected
as ``token_invalid``: letting the token choose the algorithm is how a symmetric
key gets used as a public key.

**Registration tells the truth about conflicts.** ``email_already_registered``
exists, and is served, even though confirming it enumerates which addresses have
accounts. The alternative — silently accepting a second registration for an
existing address — makes the enumeration pointless while breaking the
identifier's meaning, and this service is not yet accepting signups from
untrusted callers. The code is part of the contract; if the exposure ever
matters, the fix is a separate "email verification required" flow, not a code
that changes meaning.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header

from .config import Settings, get_settings
from .errors import ApiError, ErrorCode
from .security import InvalidPassword, hash_password, needs_rehash, verify_password

logger = logging.getLogger("dina.auth")

#: Header carrying the token. The scheme is fixed, and a token that arrives with
#: any other scheme is not ours.
AUTHORIZATION_HEADER = "Authorization"
BEARER_SCHEME = "bearer"

#: Token type claim, and the only subject claim this service issues.
TOKEN_TYPE = "access"
SUBJECT_CLAIM = "sub"

#: A user's email is compared case-insensitively and stored lowercased: two
#: spellings of the same address are one account, and a duplicate that differs
#: only in case would be a lockout the owner cannot explain.
MIN_EMAIL_LENGTH = 3
MAX_EMAIL_LENGTH = 254


@dataclass(frozen=True)
class User:
    """One account: its id, its normalised email and its Argon2id hash."""

    user_id: int
    email: str
    password_hash: str
    is_active: bool = True


def normalise_email(email: str) -> str:
    """Lowercase and trim ``email``, rejecting the shapes that cannot be one.

    The check is deliberately shape-only — one ``@``, something either side, no
    whitespace. Deciding what constitutes a deliverable address is the mail
    layer's job, and a stricter rule here would reject addresses that are
    perfectly legal and leave the user with no way to sign in.
    """
    candidate = email.strip().lower() if isinstance(email, str) else ""
    if not candidate or len(candidate) < MIN_EMAIL_LENGTH:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR, "email must not be blank", {"field": "email"}
        )
    if len(candidate) > MAX_EMAIL_LENGTH:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"email must be at most {MAX_EMAIL_LENGTH} characters",
            {"field": "email"},
        )
    local, separator, domain = candidate.partition("@")
    if not separator or not local or not domain or "." not in domain:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "email must be of the form name@example.com",
            {"field": "email"},
        )
    if any(character.isspace() for character in candidate):
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            "email must not contain whitespace",
            {"field": "email"},
        )
    return candidate


class UserDirectory:
    """Users of the service, in process.

    The same trade-off as :mod:`src.accounting_store`: the PostgreSQL
    repositories replace this, and the codes a caller sees do not change. Password
    hashes are written through :func:`src.security.hash_password` and read back
    only through :func:`src.security.verify_password`; this class never sees a
    plaintext password after the call that supplied it.
    """

    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}
        self._by_id: dict[int, User] = {}
        self._next_user_id = 1

    def register(self, email: str, password: str) -> User:
        """Create a user, or raise ``email_already_registered``.

        Raises:
            ApiError: ``validation_error`` for a malformed email or a password
                the hash policy refuses (:class:`src.security.InvalidPassword`),
                ``email_already_registered`` when the address is taken.
        """
        normalised = normalise_email(email)
        if normalised in self._by_email:
            raise ApiError(
                ErrorCode.EMAIL_ALREADY_REGISTERED,
                "an account already exists for this email address",
                {"field": "email"},
            )
        try:
            password_hash = hash_password(password)
        except InvalidPassword as exc:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                str(exc),
                {"field": "password"},
            ) from exc
        user = User(
            user_id=self._next_user_id, email=normalised, password_hash=password_hash
        )
        self._next_user_id += 1
        self._by_email[normalised] = user
        self._by_id[user.user_id] = user
        return user

    def authenticate(self, email: str, password: str) -> User:
        """Return the user for these credentials, or raise ``invalid_credentials``.

        A wrong email and a wrong password produce the *same* error, and the
        comparison runs against a dummy hash when the address is unknown, so the
        response time does not tell an attacker which addresses are registered.
        Failing closed also matters here more than usual: this is the one place
        where a distinction between the two mistakes is worth a password guess.
        """
        try:
            candidate = normalise_email(email)
        except ApiError:
            candidate = ""
        user = self._by_email.get(candidate)
        if user is None:
            _burn_password_comparison(password)
            raise ApiError(
                ErrorCode.INVALID_CREDENTIALS,
                "the email or password is incorrect",
            )
        if not user.is_active or not verify_password(password, user.password_hash):
            raise ApiError(
                ErrorCode.INVALID_CREDENTIALS,
                "the email or password is incorrect",
            )
        if needs_rehash(password, user.password_hash):
            # Upgraded in place under the same user id: a login must not change
            # who the caller is, only how the secret is stored.
            refreshed = User(
                user_id=user.user_id,
                email=user.email,
                password_hash=hash_password(password),
                is_active=user.is_active,
            )
            self._by_email[refreshed.email] = refreshed
            self._by_id[refreshed.user_id] = refreshed
        return user

    def get(self, user_id: int) -> User | None:
        return self._by_id.get(user_id)


def _burn_password_comparison(password: str) -> None:
    """Spend one Argon2id verification on a user that does not exist.

    Without this, "no such user" returns in microseconds and "wrong password" in
    tens of milliseconds, and that gap enumerates the user table. The work is
    thrown away; only its cost matters.
    """
    try:
        hash_password(password)
    except InvalidPassword:
        # A password the policy would refuse costs nothing to verify, so there
        # is no timing signal to equalise against.
        return


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _from_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(message: bytes, settings: Settings) -> bytes:
    algorithm = settings.jwt_algorithm
    digests = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}
    digest = digests[algorithm]
    return hmac.new(
        settings.require_secret_key().encode("utf-8"), message, digest
    ).digest()


def issue_access_token(
    user_id: int, settings: Settings | None = None, expires_in: timedelta | None = None
) -> str:
    """Mint a signed access token for ``user_id``.

    The lifetime comes from the settings, so one deployment-wide number governs
    every token; ``expires_in`` exists for tests that need a token that expired a
    minute ago.
    """
    settings = settings or get_settings()
    lifetime = expires_in or timedelta(minutes=settings.jwt_expire_minutes)
    now = datetime.now(timezone.utc)
    header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
    payload = {
        SUBJECT_CLAIM: str(user_id),
        "type": TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
    }
    segments = [
        _base64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    segments.append(_base64url(_sign(signing_input, settings)))
    return ".".join(segments)


def decode_access_token(token: str, settings: Settings | None = None) -> int:
    """Return the user id ``token`` proves, or raise.

    Raises:
        ApiError: ``token_invalid`` for a malformed token, a wrong signature, a
            non-``access`` token or an unparsable subject; ``token_expired`` for
            a correctly signed token whose ``exp`` is in the past.
    """
    settings = settings or get_settings()
    invalid = ApiError(
        ErrorCode.TOKEN_INVALID, "the access token is not valid", None, status_code=401
    )
    segments = token.split(".") if isinstance(token, str) else []
    if len(segments) != 3:
        raise invalid
    signing_input = ".".join(segments[:2]).encode("ascii", errors="ignore")
    expected = _base64url(_sign(signing_input, settings))
    # compare_digest on the two signature strings: constant time in the length of
    # the match, so a wrong signature cannot be found a byte at a time.
    if not hmac.compare_digest(expected, segments[2]):
        raise invalid
    try:
        header = json.loads(_from_base64url(segments[0]))
        payload = json.loads(_from_base64url(segments[1]))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise invalid from exc
    if not isinstance(payload, dict) or payload.get("type") != TOKEN_TYPE:
        raise invalid
    # The algorithm is re-checked after decoding for the same reason it is not
    # read from the token above: a token that says anything but the configured
    # algorithm is not one this service issued.
    if not isinstance(header, dict) or header.get("alg") != settings.jwt_algorithm:
        raise invalid
    subject = payload.get(SUBJECT_CLAIM)
    if subject is None:
        raise invalid
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise invalid from exc

    expires_at = payload.get("exp")
    if expires_at is None:
        raise invalid
    try:
        expiry = datetime.fromtimestamp(float(expires_at), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise invalid from exc
    if expiry <= datetime.now(timezone.utc):
        raise ApiError(
            ErrorCode.TOKEN_EXPIRED,
            "the access token has expired; sign in again",
            {"expired_at": expiry.isoformat()},
            status_code=401,
        )
    return user_id


def bearer_token(
    authorization: str | None = Header(default=None, alias=AUTHORIZATION_HEADER),
) -> str:
    """Pull the token out of the ``Authorization: Bearer <token>`` header.

    Raises:
        ApiError: ``token_invalid`` when the header is missing, uses another
            scheme, or carries no token. A missing header is deliberately *not*
            ``not_authenticated``: this dependency is the token path, and the
            provisional identity seam in :mod:`src.identity` is what reports
            ``not_authenticated`` for a request that carries no identity at all.
    """
    if not authorization or not authorization.strip():
        raise ApiError(
            ErrorCode.TOKEN_INVALID,
            "an Authorization: Bearer <token> header is required",
            status_code=401,
        )
    scheme, separator, token = authorization.strip().partition(" ")
    if not separator or scheme.strip().lower() != BEARER_SCHEME or not token.strip():
        raise ApiError(
            ErrorCode.TOKEN_INVALID,
            "the Authorization header must use the Bearer scheme",
            status_code=401,
        )
    return token.strip()


def token_user_id(
    token: str = Depends(bearer_token), settings: Settings = Depends(get_settings)
) -> int:
    """FastAPI dependency: the user id a bearer token proves.

    A dependency of :func:`bearer_token`, so a request that cannot even present a
    token is rejected before this runs.
    """
    return decode_access_token(token, settings)
