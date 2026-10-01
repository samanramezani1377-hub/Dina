"""Role ranking and the permission checks the API enforces.

The spec requires that access is decided by the backend and not by hiding
buttons in the UI, so every ledger read resolves the caller's role server-side
and refuses anything below the accounting threshold.

Roles form a ladder rather than a flat set, because the spec asks for
"accounting roles and above" and "above" only means something if the roles are
ordered. :data:`ROLE_RANK` is that order, lowest first:

``viewer`` < ``sales`` = ``warehouse`` < ``accountant`` < ``manager`` < ``owner``

Two entries share a rank on purpose: a sales clerk and a warehouse clerk are
neither more nor less privileged than one another, and inventing a false
ordering between them would let one of them read the other's reports.

An unrecognised role ranks below every known role and therefore fails every
check. A role name that arrives from a stale token or a typo in a database must
not be treated as permissive, and failing open here would hand a stranger the
whole chart of accounts.
"""

from __future__ import annotations

#: Roles from lowest to highest privilege. See the module docstring.
ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "sales": 1,
    "warehouse": 1,
    "accountant": 2,
    "manager": 3,
    "owner": 4,
}

#: Reading the ledger needs at least this rank. Posting a journal entry is the
#: same threshold; a viewer may look at a balance but may not move one.
ACCOUNTING_ROLE = "accountant"


def role_rank(role: str | None) -> int:
    """Rank of ``role``. Unknown or missing roles rank below every real role."""
    if role is None:
        return -1
    return ROLE_RANK.get(role.strip().lower(), -1)


def has_role(user_role: str | None, required: str = ACCOUNTING_ROLE) -> bool:
    """Whether ``user_role`` is at or above ``required`` in :data:`ROLE_RANK`."""
    return role_rank(user_role) >= ROLE_RANK[required]