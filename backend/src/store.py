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

    def owner_count(self, organization_id: int) -> int:
        return sum(
            1 for membership in self.memberships
            if membership.organization_id == organization_id and membership.role == "owner"
        )

    def add_membership(self, user_id: int, organization_id: int, role: str) -> None:
        if organization_id not in self.organizations:
            raise ValueError("organization does not exist")
        previous = self.user_role(user_id, organization_id)
        if previous == "owner" and role != "owner" and self.owner_count(organization_id) <= 1:
            raise ValueError("cannot demote the last organization owner")
        self.memberships = [
            membership for membership in self.memberships
            if not (membership.user_id == user_id and membership.organization_id == organization_id)
        ]
        self.memberships.append(Membership(user_id, organization_id, role))

    def remove_membership(self, user_id: int, organization_id: int) -> None:
        previous = self.user_role(user_id, organization_id)
        if previous == "owner" and self.owner_count(organization_id) <= 1:
            raise ValueError("cannot remove the last organization owner")
        self.memberships = [
            membership for membership in self.memberships
            if not (membership.user_id == user_id and membership.organization_id == organization_id)
        ]

    def can_access(self, user_id: int, organization_id: int) -> bool:
        return self.user_role(user_id, organization_id) is not None
