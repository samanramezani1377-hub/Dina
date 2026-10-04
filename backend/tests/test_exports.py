from src.main import app
def test_formal_export_routes_are_mounted():
    routes={(r.path,tuple(sorted(r.methods or []))) for r in app.routes}
    assert any("/exports/trial-balance.xlsx" in p for p,_ in routes)
    assert any("/exports/ledger.pdf" in p for p,_ in routes)
    assert any("/exports/sales.xlsx" in p for p,_ in routes)
