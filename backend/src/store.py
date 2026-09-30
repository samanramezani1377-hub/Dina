from dataclasses import dataclass
from .models import Membership, Organization

@dataclass
class InMemoryStore:
    organizations: dict[int, Organization]
    memberships: list[Membership]

    def user_role(self, user_id: int, organization_id: int) -> str | None:
        for membership in self.memberships:
            if membership.user_id == user_id and membership.organization_id == organization_id:
                return membership.role
        return None

    def can_access(self, user_id: int, organization_id: int) -> bool:
        return self.user_role(user_id, organization_id) is not None
