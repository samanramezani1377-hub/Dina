from src.main import app

def test_platform_settings_routes_are_mounted():
    paths={r.path for r in app.routes}
    assert "/api/v1/platform/settings" in paths
    assert "/api/v1/platform/settings/{key}" in paths
