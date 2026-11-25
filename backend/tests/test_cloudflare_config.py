from types import SimpleNamespace

from src import config


def test_cloudflare_bindings_supply_secret_and_hyperdrive_url(monkeypatch):
    runtime_env = SimpleNamespace(
        ENVIRONMENT="production",
        SECRET_KEY="test-only-secret-key-with-at-least-32-characters",
        JWT_ALGORITHM="HS256",
        JWT_EXPIRE_MINUTES="60",
        HYPERDRIVE=SimpleNamespace(
            connection_string="postgresql://test_user:test_password@db.example.test:5432/dina_test"
        ),
        ZARINPAL_SANDBOX="true",
    )
    monkeypatch.setattr(config, "_cloudflare_env", runtime_env)
    config.reset_settings_cache()

    try:
        settings = config.get_settings()
        assert settings.environment == "production"
        assert settings.require_secret_key() == runtime_env.SECRET_KEY
        assert settings.database_url == runtime_env.HYPERDRIVE.connection_string
        assert settings.zarinpal_sandbox is True
    finally:
        config.reset_settings_cache()
