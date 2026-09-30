from fastapi.testclient import TestClient
from src.main import app
client=TestClient(app)
def test_balanced():
 r=client.post('/api/v1/accounting/journals/validate',json={'organization_id':1,'document_no':'JV-1','description':'sale','lines':[{'account_id':1,'debit':'100','credit':'0'},{'account_id':2,'debit':'0','credit':'100'}]})
 assert r.status_code==200 and r.json()['valid'] is True
def test_unbalanced():
 r=client.post('/api/v1/accounting/journals/validate',json={'organization_id':1,'document_no':'JV-2','description':'bad','lines':[{'account_id':1,'debit':'100','credit':'0'},{'account_id':2,'debit':'0','credit':'90'}]})
 assert r.status_code==422 and r.json()['detail']=='journal_not_balanced'
