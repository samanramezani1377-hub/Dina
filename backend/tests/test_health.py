def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_the_configured_service(client) -> None:
    response = client.get("/health")
    assert response.json()["service"] == "dina-api"


def test_health_runs_under_a_booted_lifespan(client) -> None:
    # The `client` fixture enters the TestClient context manager, so the
    # fail-fast settings gate in src.main.lifespan really ran for this suite.
    assert client.app.state.settings.is_test is True
