from src.main import app

def test_platform_admin_routes_are_mounted():
    routes = {(route.path, tuple(sorted(route.methods or ()))) for route in app.routes}
    assert ("/api/v1/platform/dashboard", ("GET",)) in routes
    assert ("/api/v1/platform/users", ("GET",)) in routes
    assert ("/api/v1/platform/plans", ("GET",)) in routes
    assert ("/api/v1/platform/plans", ("POST",)) in routes
    assert ("/api/v1/platform/payments", ("GET",)) in routes
    assert ("/api/v1/platform/billing", ("GET",)) in routes
