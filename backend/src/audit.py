"""Append-only audit trail for sensitive operations.

Every sensitive operation in Dina goes through :func:`record`. The service has
three hard guarantees:

1. **No secrets.** Metadata is passed through a redaction layer
   (:func:`redact`) before it is serialised. A caller cannot persist a
   password, a password hash, a token or an authorization header even by
   accident.
2. **Never breaks the business operation.** If the audit write fails the
   failure is logged (with a traceback) and ``record`` returns ``None``. The
   user request still succeeds.
3. **Append-only.** Stores expose no update or delete path. The PostgreSQL
   migration additionally revokes UPDATE/DELETE for the application role and
   installs a trigger that rejects them.

Redaction is deliberately applied twice: once per key/value while walking the
metadata tree, and once as a final pattern scan over the serialised form. The
second pass is the backstop that makes "a caller cannot accidentally persist a
secret" true even for shapes the first pass does not model.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

logger = logging.getLogger("dina.audit")

REDACTED = "[REDACTED]"

#: Maximum depth walked while redacting, guards against pathological nesting.
MAX_DEPTH = 12

#: Maximum length of a serialised metadata payload, keeps rows bounded.
MAX_METADATA_CHARS = 8000


class AuditAction:
    """Stable action names. These are part of the public contract."""

    LOGIN_SUCCEEDED = "auth.login_succeeded"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    ORGANIZATION_CREATED = "organization.created"
    MEMBERSHIP_ADDED = "membership.added"
    MEMBERSHIP_REMOVED = "membership.removed"
    ACCOUNT_CREATED = "account.created"
    ACCOUNT_DEACTIVATED = "account.deactivated"
    JOURNAL_CREATED = "journal.created"
    JOURNAL_POSTED = "journal.posted"
    JOURNAL_REVERSED = "journal.reversed"
    JOURNAL_CORRECTED = "journal.corrected"
    PAYMENT_RECORDED = "payment.recorded"
    SUBSCRIPTION_CHANGED = "subscription.changed"


class AuditError(Exception):
    """Raised by query helpers on permission or tenancy violations."""


# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------

#: Key names that always redact, matched after stripping _ - . and lowercasing.
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "newpassword",
        "oldpassword",
        "currentpassword",
        "passwordhash",
        "passworddigest",
        "hash",
        "digest",
        "salt",
        "token",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "bearertoken",
        "jwttoken",
        "apikey",
        "apisecret",
        "secret",
        "clientsecret",
        "authorization",
        "authheader",
        "cookie",
        "setcookie",
        "session",
        "sessionid",
        "privatekey",
        "secretkey",
        "signature",
        "credential",
        "credentials",
        "otp",
        "pin",
    }
)

#: Substrings that make a key sensitive (e.g. ``user_password_hash``).
SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "authorization",
    "privatekey",
    "credential",
    "sessionid",
    "cookie",
    "jwt",
    "bearer",
)

#: Value shapes that look like a secret even when the key is innocuous.
SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # JWT: three base64url segments.
    re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b"),
    # Password hashes we might ever be handed.
    re.compile(r"\$argon2[a-z]{0,2}\$[\w$/.+=]{8,}"),
    re.compile(r"\$(2[aby]|scrypt)\$[\w$/.+=]{8,}"),
    # bcrypt / sha / md5 style digests.
    re.compile(r"\$(?:sha(?:1|224|256|384|512)|md5)\$?[\w$/.+=]{16,}"),
    re.compile(r"\b[a-f0-9]{32,}\b", re.IGNORECASE),
    # key=value pairs embedded in a message.
    re.compile(
        r"(?i)\b(?:password|passwd|pwd|token|secret|api[_-]?key|authorization|bearer)\b"
        r"\s*[:=]\s*\S+"
    ),
    # "Authorization: Bearer xxxx" / "password is hunter2" style prose.
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"(?i)\b(?:password|token|secret)\s+(?:is|was)\s+\S+"),
)


def _normalize_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def is_sensitive_key(key: object) -> bool:
    normalized = _normalize_key(key)
    if not normalized:
        return False
    if normalized in SENSITIVE_KEYS:
        return True
    return any(part in normalized for part in SENSITIVE_KEY_SUBSTRINGS)


def contains_secret_value(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS)


def redact(value: Any, *, _depth: int = 0) -> Any:
    """Return ``value`` with every secret-looking part replaced by REDACTED."""
    if _depth > MAX_DEPTH:
        return REDACTED
    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Decimal):
        return _redact_string(str(value))
    if isinstance(value, (datetime, UUID)):
        return value.isoformat()
    if isinstance(value, bytes):
        return REDACTED
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if is_sensitive_key(name):
                out[name] = REDACTED
            else:
                out[name] = redact(item, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item, _depth=_depth + 1) for item in value]
    return _redact_string(str(value))


def _redact_string(value: str) -> str:
    result = value
    for pattern in SECRET_VALUE_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def _scan_and_blank(text: str) -> str | None:
    """Return the sanitised text, or ``None`` if it still leaks a secret.

    Backstop pass. Anything that survives this check is discarded wholesale:
    a half-redacted secret is worse than a missing audit detail.
    """
    if contains_secret_value(text):
        return None
    if len(text) > MAX_METADATA_CHARS:
        text = text[:MAX_METADATA_CHARS] + REDACTED
    return text


# --------------------------------------------------------------------------
# Entries and stores
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditEntry:
    """One immutable audit row."""

    id: int
    organization_id: int | None
    user_id: int | None
    action: str
    entity: str
    entity_id: str | None
    occurred_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    ip_address: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "user_id": self.user_id,
            "action": self.action,
            "entity": self.entity,
            "entity_id": self.entity_id,
            "occurred_at": self.occurred_at.isoformat(),
            "metadata": self.metadata,
            "correlation_id": self.correlation_id,
            "ip_address": self.ip_address,
        }


class AuditStore:
    """Append-only store interface. Deliberately no update/delete methods."""

    def append(self, entry: AuditEntry) -> AuditEntry:  # pragma: no cover
        raise NotImplementedError

    def list_for_organization(self, organization_id: int) -> list[AuditEntry]:
        raise NotImplementedError  # pragma: no cover

    def list_for_action(self, action: str) -> list[AuditEntry]:
        raise NotImplementedError  # pragma: no cover


class InMemoryAuditStore(AuditStore):
    """In-memory store used by unit tests and by the validate-only API.

    It mirrors the SQL schema (including tenant filtering) but holds nothing
    across process restarts.
    """

    def __init__(self) -> None:
        self._rows: list[AuditEntry] = []
        self._next_id = 1

    def append(self, entry: AuditEntry) -> AuditEntry:
        stored = AuditEntry(
            id=self._next_id,
            organization_id=entry.organization_id,
            user_id=entry.user_id,
            action=entry.action,
            entity=entry.entity,
            entity_id=entry.entity_id,
            occurred_at=entry.occurred_at,
            metadata=entry.metadata,
            correlation_id=entry.correlation_id,
            ip_address=entry.ip_address,
        )
        self._next_id += 1
        self._rows.append(stored)
        return stored

    def list_for_organization(self, organization_id: int) -> list[AuditEntry]:
        return [r for r in self._rows if r.organization_id == organization_id]

    def list_for_action(self, action: str) -> list[AuditEntry]:
        return [r for r in self._rows if r.action == action]

    @property
    def rows(self) -> list[AuditEntry]:
        return list(self._rows)

    def clear(self) -> None:
        """Drop every row. In-memory only, for test isolation."""
        self._rows.clear()
        self._next_id = 1


class PostgresAuditStore(AuditStore):
    """Append-only store backed by the ``audit_logs`` table.

    ``connect`` is any callable returning a DB-API 2.0 connection (psycopg,
    psycopg2). Append-only is additionally enforced by the migration: UPDATE
    and DELETE are revoked for the application role and rejected by a trigger.
    """

    def __init__(self, connect) -> None:
        self._connect = connect

    def append(self, entry: AuditEntry) -> AuditEntry:
        sql = """
            INSERT INTO audit_logs
                (organization_id, user_id, action, entity, entity_id,
                 occurred_at, metadata, correlation_id, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        entry.organization_id,
                        entry.user_id,
                        entry.action,
                        entry.entity,
                        entry.entity_id,
                        entry.occurred_at,
                        json.dumps(entry.metadata),
                        entry.correlation_id,
                        entry.ip_address,
                    ),
                )
                new_id = cur.fetchone()[0]
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return AuditEntry(
            id=new_id,
            organization_id=entry.organization_id,
            user_id=entry.user_id,
            action=entry.action,
            entity=entry.entity,
            entity_id=entry.entity_id,
            occurred_at=entry.occurred_at,
            metadata=entry.metadata,
            correlation_id=entry.correlation_id,
            ip_address=entry.ip_address,
        )

    def list_for_organization(self, organization_id: int) -> list[AuditEntry]:
        return self._query(
            """SELECT id, organization_id, user_id, action, entity, entity_id,
                      occurred_at, metadata, correlation_id, ip_address
                 FROM audit_logs
                WHERE organization_id = %s
                ORDER BY id ASC""",
            (organization_id,),
        )

    def list_for_action(self, action: str) -> list[AuditEntry]:
        return self._query(
            """SELECT id, organization_id, user_id, action, entity, entity_id,
                      occurred_at, metadata, correlation_id, ip_address
                 FROM audit_logs
                WHERE action = %s
                ORDER BY id ASC""",
            (action,),
        )

    def _query(self, sql: str, params: Sequence[Any]) -> list[AuditEntry]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        finally:
            conn.close()
        return [
            AuditEntry(
                id=row[0],
                organization_id=row[1],
                user_id=row[2],
                action=row[3],
                entity=row[4],
                entity_id=row[5],
                occurred_at=row[6],
                metadata=row[7] if isinstance(row[7], dict) else json.loads(row[7] or "{}"),
                correlation_id=row[8],
                ip_address=row[9],
            )
            for row in rows
        ]


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------

DEFAULT_STORE = InMemoryAuditStore()


def _coerce_entity_id(entity_id: Any) -> str | None:
    if entity_id is None:
        return None
    return str(entity_id)


def _normalise_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    redacted = redact(dict(metadata))
    serialised = json.dumps(redacted, default=str, sort_keys=True)
    safe = _scan_and_blank(serialised)
    if safe is None:
        # Backstop tripped: keep the entry, drop every detail.
        logger.warning("audit metadata dropped by redaction backstop")
        return {"metadata_dropped": True, "redaction_applied": True}
    try:
        restored = json.loads(safe)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return {"metadata_unavailable": True}
    return restored if isinstance(restored, dict) else {"value": restored}


def record(
    *,
    action: str,
    entity: str,
    entity_id: Any = None,
    organization_id: int | None = None,
    user_id: int | None = None,
    metadata: Mapping[str, Any] | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
    store: AuditStore | None = None,
    occurred_at: datetime | None = None,
) -> AuditEntry | None:
    """Append one audit row. Never raises; returns ``None`` if the write failed.

    ``organization_id`` is nullable so system-level events (a login that never
    resolved to a tenant, for instance) are still recorded.
    """
    target = store if store is not None else DEFAULT_STORE
    safe_metadata = _normalise_metadata(metadata)
    safe_correlation_id = _redact_string(correlation_id) if correlation_id else None
    safe_ip = _redact_string(ip_address) if ip_address else None
    entry = AuditEntry(
        id=0,
        organization_id=organization_id,
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=_coerce_entity_id(entity_id),
        occurred_at=occurred_at or datetime.now(timezone.utc),
        metadata=safe_metadata,
        correlation_id=safe_correlation_id,
        ip_address=safe_ip,
    )
    try:
        return target.append(entry)
    except Exception:
        # Audit must never break the business operation, but the failure has to
        # be visible in the logs.
        logger.exception(
            "audit write failed: action=%s entity=%s entity_id=%s organization_id=%s user_id=%s",
            action,
            entity,
            entry.entity_id,
            organization_id,
            user_id,
        )
        return None


# --------------------------------------------------------------------------
# Querying
# --------------------------------------------------------------------------

#: Roles allowed to read an organization's audit trail.
AUDIT_READ_ROLES = frozenset({"owner", "manager"})


def query_for_organization(
    store: AuditStore,
    organization_id: int,
    *,
    role: str | None = None,
    user_id: int | None = None,
    action: str | None = None,
) -> list[AuditEntry]:
    """Return the audit rows of one organization for an authorized reader.

    The organization id comes from the caller's authorization context, never
    from a user supplied filter, and only the roles in
    :data:`AUDIT_READ_ROLES` may read the trail. Any other caller raises
    :class:`AuditError`, so a cross-tenant read is impossible rather than
    merely empty.
    """
    if organization_id is None:
        raise AuditError("organization_id is required")
    if role not in AUDIT_READ_ROLES:
        raise AuditError("role may not read the audit trail")
    rows = store.list_for_organization(organization_id)
    if action is not None:
        rows = [r for r in rows if r.action == action]
    if user_id is not None:
        rows = [r for r in rows if r.user_id == user_id]
    return rows


# --------------------------------------------------------------------------
# Call-site helpers. One per sensitive operation, so a route handler never has
# to remember to redact anything.
# --------------------------------------------------------------------------


def _common(
    *,
    entity: str,
    entity_id: Any,
    user_id: int | None,
    organization_id: int | None,
    metadata: Mapping[str, Any] | None,
    store: AuditStore | None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    return {
        "entity": entity,
        "entity_id": entity_id,
        "user_id": user_id,
        "organization_id": organization_id,
        "metadata": metadata,
        "store": store,
        "correlation_id": correlation_id,
        "ip_address": ip_address,
    }


def record_login_succeeded(
    *,
    user_id: int,
    organization_id: int | None = None,
    email: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    store: AuditStore | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
) -> AuditEntry | None:
    details: dict[str, Any] = dict(metadata or {})
    if email:
        details["email"] = email
    return record(
        action=AuditAction.LOGIN_SUCCEEDED,
        **_common(
            entity="user",
            entity_id=user_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata=details or None,
            store=store,
            correlation_id=correlation_id,
            ip_address=ip_address,
        ),
    )


def record_login_failed(
    *,
    email: str | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
    reason_code: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    store: AuditStore | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
) -> AuditEntry | None:
    details: dict[str, Any] = dict(metadata or {})
    if email:
        details["email"] = email
    if reason_code:
        details["reason_code"] = reason_code
    return record(
        action=AuditAction.LOGIN_FAILED,
        **_common(
            entity="user",
            entity_id=user_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata=details or None,
            store=store,
            correlation_id=correlation_id,
            ip_address=ip_address,
        ),
    )


def record_logout(*, user_id: int, organization_id: int | None = None, **kwargs) -> AuditEntry | None:
    return record(
        action=AuditAction.LOGOUT,
        **_common(
            entity="user",
            entity_id=user_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata=None,
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_organization_created(
    *, organization_id: int, user_id: int, name: str | None = None, **kwargs
) -> AuditEntry | None:
    return record(
        action=AuditAction.ORGANIZATION_CREATED,
        **_common(
            entity="organization",
            entity_id=organization_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata={"name": name} if name else None,
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_membership_added(
    *, organization_id: int, user_id: int, member_user_id: int, role: str, **kwargs
) -> AuditEntry | None:
    return record(
        action=AuditAction.MEMBERSHIP_ADDED,
        **_common(
            entity="membership",
            entity_id=f"{organization_id}:{member_user_id}",
            user_id=user_id,
            organization_id=organization_id,
            metadata={"member_user_id": member_user_id, "role": role},
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_membership_removed(
    *, organization_id: int, user_id: int, member_user_id: int, role: str | None = None, **kwargs
) -> AuditEntry | None:
    return record(
        action=AuditAction.MEMBERSHIP_REMOVED,
        **_common(
            entity="membership",
            entity_id=f"{organization_id}:{member_user_id}",
            user_id=user_id,
            organization_id=organization_id,
            metadata={"member_user_id": member_user_id, "role": role},
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_account_created(
    *,
    organization_id: int,
    user_id: int,
    account_id: int,
    code: str,
    account_type: str,
    **kwargs,
) -> AuditEntry | None:
    return record(
        action=AuditAction.ACCOUNT_CREATED,
        **_common(
            entity="account",
            entity_id=account_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata={"code": code, "account_type": account_type},
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_journal_created(
    *,
    organization_id: int,
    user_id: int,
    journal_id: int,
    document_no: str,
    line_count: int,
    **kwargs,
) -> AuditEntry | None:
    return record(
        action=AuditAction.JOURNAL_CREATED,
        **_common(
            entity="journal_entry",
            entity_id=journal_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata={"document_no": document_no, "line_count": line_count},
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_journal_posted(
    *,
    organization_id: int,
    user_id: int,
    journal_id: int,
    document_no: str,
    **kwargs,
) -> AuditEntry | None:
    return record(
        action=AuditAction.JOURNAL_POSTED,
        **_common(
            entity="journal_entry",
            entity_id=journal_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata={"document_no": document_no},
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_journal_reversed(
    *,
    organization_id: int,
    user_id: int,
    journal_id: int,
    reversal_id: int,
    document_no: str,
    **kwargs,
) -> AuditEntry | None:
    return record(
        action=AuditAction.JOURNAL_REVERSED,
        **_common(
            entity="journal_entry",
            entity_id=journal_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata={"document_no": document_no, "reversal_id": reversal_id},
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_journal_corrected(
    *,
    organization_id: int,
    user_id: int,
    journal_id: int,
    correction_id: int,
    document_no: str,
    **kwargs,
) -> AuditEntry | None:
    return record(
        action=AuditAction.JOURNAL_CORRECTED,
        **_common(
            entity="journal_entry",
            entity_id=journal_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata={"document_no": document_no, "correction_id": correction_id},
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_payment_recorded(
    *,
    organization_id: int,
    user_id: int,
    payment_id: int,
    amount: str,
    currency: str | None = None,
    **kwargs,
) -> AuditEntry | None:
    return record(
        action=AuditAction.PAYMENT_RECORDED,
        **_common(
            entity="payment",
            entity_id=payment_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata={"amount": amount, "currency": currency},
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


def record_subscription_changed(
    *,
    organization_id: int,
    user_id: int,
    subscription_id: int,
    change: str,
    status: str | None = None,
    **kwargs,
) -> AuditEntry | None:
    return record(
        action=AuditAction.SUBSCRIPTION_CHANGED,
        **_common(
            entity="subscription",
            entity_id=subscription_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata={"change": change, "status": status},
            store=kwargs.get("store"),
            correlation_id=kwargs.get("correlation_id"),
            ip_address=kwargs.get("ip_address"),
        ),
    )


ALL_HELPERS: Iterable[str] = (
    "record_login_succeeded",
    "record_login_failed",
    "record_logout",
    "record_organization_created",
    "record_membership_added",
    "record_membership_removed",
    "record_account_created",
    "record_journal_created",
    "record_journal_posted",
    "record_journal_reversed",
    "record_journal_corrected",
    "record_payment_recorded",
    "record_subscription_changed",
)
