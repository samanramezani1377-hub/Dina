from dataclasses import dataclass
from decimal import Decimal
@dataclass(frozen=True)
class Organization: id: int; name: str
@dataclass(frozen=True)
class Membership: user_id: int; organization_id: int; role: str
@dataclass(frozen=True)
class JournalLine: account_id: int; debit: Decimal; credit: Decimal
