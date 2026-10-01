"""PostgreSQL-backed repositories used by production.

The public methods intentionally mirror the in-memory repositories so domain
logic and report builders do not know which persistence engine is active.
Every write is transactional and every read carries the organization id into
the SQL predicate; tenant scope is never a caller-side convention.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from .accounting import validate_journal
from .accounting_store import AccountingError
from .auth import User, normalise_email
from .errors import ApiError, ErrorCode
from .models import (
    ACCOUNT_TYPES, DRAFT, LEDGER_STATUSES, POSTED, REVERSED,
    Account, EntryLine, JournalEntry, JournalLine, Membership, Organization,
)
from .money import to_money
from .security import hash_password, needs_rehash, verify_password


def _dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


class PostgresStore:
    """Durable organization, membership, account and journal repository."""

    def __init__(self, database_url: str) -> None:
        self.database_url = _dsn(database_url)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    # organization / membership seam used by identity.py
    @property
    def organizations(self) -> dict[int, Organization]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, name FROM organizations ORDER BY id").fetchall()
        return {int(r["id"]): Organization(id=int(r["id"]), name=r["name"]) for r in rows}

    def user_role(self, user_id: int, organization_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT role FROM memberships WHERE user_id=%s AND organization_id=%s",
                (user_id, organization_id),
            ).fetchone()
        return None if row is None else str(row["role"])

    def can_access(self, user_id: int, organization_id: int) -> bool:
        return self.user_role(user_id, organization_id) is not None

    def add_organization(self, organization_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM organizations WHERE id=%s", (organization_id,)
            ).fetchone()
            if row is None:
                raise AccountingError(
                    ErrorCode.ORGANIZATION_NOT_FOUND,
                    f"organization {organization_id} does not exist",
                )

    # accounting repository
    def organization_exists(self, organization_id: int) -> bool:
        with self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM organizations WHERE id=%s", (organization_id,)
            ).fetchone() is not None

    def _require_org(self, organization_id: int) -> None:
        if not self.organization_exists(organization_id):
            raise AccountingError(
                ErrorCode.ORGANIZATION_NOT_FOUND,
                f"organization {organization_id} does not exist",
            )

    def add_account(self, organization_id: int, code: str, name: str, account_type: str) -> Account:
        self._require_org(organization_id)
        account_type = account_type.strip().lower()
        if account_type not in ACCOUNT_TYPES:
            raise AccountingError(ErrorCode.INVALID_ACCOUNT_TYPE, "invalid account type")
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """INSERT INTO accounts (organization_id,code,name,account_type)
                       VALUES (%s,%s,%s,%s)
                       RETURNING id,organization_id,code,name,account_type""",
                    (organization_id, code, name, account_type),
                ).fetchone()
        except psycopg.errors.UniqueViolation as exc:
            raise AccountingError(
                ErrorCode.ACCOUNT_CODE_CONFLICT,
                f"account code {code} already exists in this organization",
            ) from exc
        return Account(**{k: (int(v) if k in {"id","organization_id"} else v) for k,v in row.items()})

    def get_account(self, organization_id: int, account_id: int) -> Account:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id,organization_id,code,name,account_type
                   FROM accounts WHERE id=%s AND organization_id=%s""",
                (account_id, organization_id),
            ).fetchone()
        if row is None:
            raise AccountingError(ErrorCode.ACCOUNT_NOT_FOUND, "account does not exist in this organization")
        return Account(**{k: (int(v) if k in {"id","organization_id"} else v) for k,v in row.items()})

    def list_accounts(self, organization_id: int) -> list[Account]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id,organization_id,code,name,account_type
                   FROM accounts WHERE organization_id=%s ORDER BY code,id""",
                (organization_id,),
            ).fetchall()
        return [Account(**{k: (int(v) if k in {"id","organization_id"} else v) for k,v in r.items()}) for r in rows]

    def _entry(self, row, lines) -> JournalEntry:
        return JournalEntry(
            id=int(row["id"]), organization_id=int(row["organization_id"]),
            document_no=row["document_no"], description=row["description"],
            status=row["status"], entry_date=row["entry_date"],
            posted_at=row["posted_at"], reversal_of_entry_id=(
                int(row["reversal_of_entry_id"]) if row["reversal_of_entry_id"] is not None else None
            ), lines=tuple(lines),
        )

    def get_entry(self, organization_id: int, entry_id: int) -> JournalEntry:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id,organization_id,document_no,description,status,
                          entry_date,posted_at,reversal_of_entry_id
                   FROM journal_entries WHERE id=%s AND organization_id=%s""",
                (entry_id, organization_id),
            ).fetchone()
            if row is None:
                raise AccountingError(ErrorCode.JOURNAL_NOT_FOUND, "journal entry does not exist in this organization")
            lines = conn.execute(
                """SELECT journal_entry_id AS entry_id,id AS line_no,account_id,debit,credit
                   FROM journal_lines WHERE journal_entry_id=%s ORDER BY id""",
                (entry_id,),
            ).fetchall()
        return self._entry(row, [
            EntryLine(entry_id=int(x["entry_id"]), line_no=int(x["line_no"]),
                      account_id=int(x["account_id"]), debit=Decimal(x["debit"]), credit=Decimal(x["credit"]))
            for x in lines
        ])

    def list_entries(self, organization_id: int) -> list[JournalEntry]:
        self._require_org(organization_id)
        with self._connect() as conn:
            ids = conn.execute(
                "SELECT id FROM journal_entries WHERE organization_id=%s ORDER BY id",
                (organization_id,),
            ).fetchall()
        return [self.get_entry(organization_id, int(x["id"])) for x in ids]

    def ledger_entries(self, organization_id: int) -> list[JournalEntry]:
        self._require_org(organization_id)
        with self._connect() as conn:
            ids = conn.execute(
                """SELECT id FROM journal_entries
                   WHERE organization_id=%s AND status = ANY(%s) ORDER BY id""",
                (organization_id, list(LEDGER_STATUSES)),
            ).fetchall()
        return [self.get_entry(organization_id, int(x["id"])) for x in ids]

    def add_entry(self, organization_id: int, document_no: str, description: str,
                  entry_date: date, lines: list[JournalLine], status: str = DRAFT,
                  reversal_of_entry_id: int | None = None) -> JournalEntry:
        self._require_org(organization_id)
        if status not in {DRAFT, POSTED, REVERSED}:
            raise AccountingError(ErrorCode.INVALID_ENTRY_STATUS, "invalid entry status")
        if not lines:
            raise AccountingError(ErrorCode.JOURNAL_EMPTY, "a journal entry must have at least one line")
        try:
            validate_journal(lines)
            with self._connect() as conn:
                for line in lines:
                    account = conn.execute(
                        "SELECT 1 FROM accounts WHERE id=%s AND organization_id=%s",
                        (line.account_id, organization_id),
                    ).fetchone()
                    if account is None:
                        raise AccountingError(ErrorCode.ACCOUNT_NOT_FOUND, "account does not exist in this organization")
                row = conn.execute(
                    """INSERT INTO journal_entries
                       (organization_id,document_no,description,status,posted_at,reversal_of_entry_id)
                       VALUES (%s,%s,%s,%s,%s,%s)
                       RETURNING id,organization_id,document_no,description,status,created_at,
                                 posted_at,reversal_of_entry_id""",
                    (organization_id, document_no, description, status,
                     datetime.now(timezone.utc) if status != DRAFT else None, reversal_of_entry_id),
                ).fetchone()
                entry_id = int(row["id"])
                for line in lines:
                    conn.execute(
                        """INSERT INTO journal_lines (journal_entry_id,account_id,debit,credit)
                           VALUES (%s,%s,%s,%s)""",
                        (entry_id, line.account_id, to_money(line.debit), to_money(line.credit)),
                    )
        except psycopg.errors.UniqueViolation as exc:
            raise AccountingError(ErrorCode.DOCUMENT_NO_CONFLICT, "document number already exists in this organization") from exc
        return self.get_entry(organization_id, entry_id)

    def post_entry(self, organization_id: int, entry_id: int) -> JournalEntry:
        with self._connect() as conn:
            row = conn.execute(
                """UPDATE journal_entries SET status='posted',posted_at=NOW()
                   WHERE id=%s AND organization_id=%s AND status='draft'
                   RETURNING id""", (entry_id, organization_id)
            ).fetchone()
        if row is None:
            entry = self.get_entry(organization_id, entry_id)
            raise AccountingError(ErrorCode.JOURNAL_IMMUTABLE, f"entry {entry.id} is {entry.status} and cannot be posted")
        return self.get_entry(organization_id, entry_id)

    def update_entry(self, organization_id: int, entry_id: int, *, description: str | None = None,
                     entry_date: date | None = None, lines: list[JournalLine] | None = None) -> JournalEntry:
        entry = self.get_entry(organization_id, entry_id)
        if entry.status != DRAFT:
            raise AccountingError(ErrorCode.JOURNAL_IMMUTABLE, "only draft entries may be edited")
        if lines is not None:
            if not lines:
                raise AccountingError(ErrorCode.JOURNAL_EMPTY, "a journal entry must have at least one line")
            validate_journal(lines)
            for line in lines:
                self.get_account(organization_id, line.account_id)
        with self._connect() as conn:
            conn.execute(
                """UPDATE journal_entries SET description=COALESCE(%s,description),
                   entry_date=COALESCE(%s,entry_date) WHERE id=%s AND organization_id=%s AND status='draft'""",
                (description, entry_date, entry_id, organization_id),
            )
            if lines is not None:
                conn.execute("DELETE FROM journal_lines WHERE journal_entry_id=%s", (entry_id,))
                for line in lines:
                    conn.execute(
                        "INSERT INTO journal_lines (journal_entry_id,account_id,debit,credit) VALUES (%s,%s,%s,%s)",
                        (entry_id, line.account_id, to_money(line.debit), to_money(line.credit)),
                    )
        return self.get_entry(organization_id, entry_id)

    def delete_entry(self, organization_id: int, entry_id: int) -> None:
        entry = self.get_entry(organization_id, entry_id)
        if entry.status != DRAFT:
            raise AccountingError(ErrorCode.JOURNAL_IMMUTABLE, "only draft entries may be deleted")
        with self._connect() as conn:
            conn.execute("DELETE FROM journal_entries WHERE id=%s AND organization_id=%s AND status='draft'",
                         (entry_id, organization_id))

    def reverse_entry(self, organization_id: int, entry_id: int, document_no: str,
                      entry_date: date, description: str = "") -> JournalEntry:
        original = self.get_entry(organization_id, entry_id)
        if original.status != POSTED:
            raise AccountingError(ErrorCode.JOURNAL_NOT_REVERSIBLE, "only a posted entry can be reversed")
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM journal_entries WHERE organization_id=%s AND reversal_of_entry_id=%s",
                (organization_id, entry_id),
            ).fetchone()
            if existing:
                raise AccountingError(ErrorCode.ENTRY_ALREADY_REVERSED, "entry has already been reversed")
            try:
                row = conn.execute(
                    """INSERT INTO journal_entries
                       (organization_id,document_no,description,status,posted_at,reversal_of_entry_id)
                       VALUES (%s,%s,%s,'posted',NOW(),%s) RETURNING id""",
                    (organization_id, document_no, description or f"reversal of {original.document_no}", entry_id),
                ).fetchone()
                new_id = int(row["id"])
                for line in original.lines:
                    conn.execute(
                        """INSERT INTO journal_lines (journal_entry_id,account_id,debit,credit)
                           VALUES (%s,%s,%s,%s)""",
                        (new_id, line.account_id, to_money(line.credit), to_money(line.debit)),
                    )
                conn.execute(
                    "UPDATE journal_entries SET status='reversed' WHERE id=%s AND organization_id=%s AND status='posted'",
                    (entry_id, organization_id),
                )
            except psycopg.errors.UniqueViolation as exc:
                raise AccountingError(ErrorCode.DOCUMENT_NO_CONFLICT, "document number already exists in this organization") from exc
        return self.get_entry(organization_id, new_id)

    # user repository used by auth routes
    def register_user(self, email: str, password: str) -> User:
        email = normalise_email(email)
        password_hash = hash_password(password)
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "INSERT INTO users(email,password_hash) VALUES (%s,%s) RETURNING id,email,password_hash,is_active",
                    (email, password_hash),
                ).fetchone()
        except psycopg.errors.UniqueViolation as exc:
            raise ApiError(ErrorCode.EMAIL_ALREADY_REGISTERED, "an account already exists for this email address",
                           {"field": "email"}) from exc
        return User(user_id=int(row["id"]), email=row["email"], password_hash=row["password_hash"], is_active=row["is_active"])

    def authenticate_user(self, email: str, password: str) -> User:
        try:
            email = normalise_email(email)
        except ApiError:
            email = ""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id,email,password_hash,is_active FROM users WHERE email=%s", (email,)
            ).fetchone()
        if row is None or not row["is_active"] or not verify_password(password, row["password_hash"] if row else hash_password(password)):
            raise ApiError(ErrorCode.INVALID_CREDENTIALS, "the email or password is incorrect")
        user = User(user_id=int(row["id"]), email=row["email"], password_hash=row["password_hash"], is_active=row["is_active"])
        if needs_rehash(password, user.password_hash):
            refreshed = hash_password(password)
            with self._connect() as conn:
                conn.execute("UPDATE users SET password_hash=%s WHERE id=%s", (refreshed, user.user_id))
            user = User(user.user_id, user.email, refreshed, user.is_active)
        return user

    def get_user(self, user_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id,email,password_hash,is_active FROM users WHERE id=%s", (user_id,)).fetchone()
        return None if row is None else User(user_id=int(row["id"]), email=row["email"], password_hash=row["password_hash"], is_active=row["is_active"])
