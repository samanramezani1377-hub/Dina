from decimal import Decimal
from datetime import date
from backend.src.business_store import BusinessStore

def test_payment_idempotency_returns_original_payment():
    store=BusinessStore()
    store._customers.append({"id":1,"organization_id":1,"name":"Test","email":None,"phone":None})
    store._invoices.append({"id":1,"organization_id":1,"customer_id":1,"invoice_no":"1","issue_date":date.today(),"due_date":None,"total":Decimal("100"),"paid":Decimal("0"),"status":"open"})
    first, inv1=store.record_payment(1,1,Decimal("25"),"card","ref","retry-1")
    second, inv2=store.record_payment(1,1,Decimal("25"),"card","ref","retry-1")
    assert first["id"]==second["id"]
    assert inv1["paid"]==Decimal("25")
    assert inv2["paid"]==Decimal("25")
    assert len(store._payments)==1
