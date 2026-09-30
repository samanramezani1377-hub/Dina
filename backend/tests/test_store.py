from src.models import Membership,Organization
from src.store import InMemoryStore
def test_membership_is_tenant_scoped():
 s=InMemoryStore({1:Organization(1,'A'),2:Organization(2,'B')},[Membership(10,1,'accountant')]); assert s.can_access(10,1); assert not s.can_access(10,2)
