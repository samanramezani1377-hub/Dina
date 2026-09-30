"""Tests for environment-driven settings and secret handling."""

import pytest

from src.config import (
    ALLOWED_JWT_ALGORITHMS,
    ConfigurationError,
    Settings,
    get_settings,
    reset_settings_cache,
)

ENV_KEYS = (
    "SECRET_KEY",
    "ENVIRONMENT",
    "JWT_ALGORITHM",
    "JWT_EXPIRE_MINUTES",
    "DATABASE_URL",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_defaults_are_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a-secret-for-tests")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_ALGORITHM", "HS512")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "15")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u@h:5432/db")
    settings = Settings()
    assert settings.secret_key.get_secret_value() == "a-secret-for-tests"
    assert settings.jwt_algorithm == "HS512"
    assert settings.jwt_expire_minutes == 15
    assert settings.database_url == "postgresql+psycopg://u@h:5432/db"
    assert settings.is_test is False


def test_production_without_secret_key_refuses_to_start():
    with pytest.raises(ConfigurationError):
        Settings(_env_file=None)


def test_blank_secret_key_refuses_to_start():
    with pytest.raises(ConfigurationError):
        Settings(secret_key="   ", _env_file=None)


def test_production_with_placeholder_secret_key_still_accepted():
    # .env.example ships a placeholder; refusing to start on the literal
    # placeholder string is not this layer's job, but the value is never blank.
    settings = Settings(secret_key="replace-me-with-a-long-random-value", _env_file=None)
    assert settings.require_secret_key() == "replace-me-with-a-long-random-value"


def test_test_environment_tolerates_missing_secret_key():
    settings = Settings(environment="test", _env_file=None)
    assert settings.is_test is True
    assert settings.ephemeral_secret_key is True
    key = settings.require_secret_key()
    assert key and key.strip()


def test_ephemeral_keys_differ_between_instances():
    first = Settings(environment="test", _env_file=None).require_secret_key()
    second = Settings(environment="test", _env_file=None).require_secret_key()
    assert first != second


def test_explicit_secret_key_in_test_environment_is_not_ephemeral():
    settings = Settings(environment="test", secret_key="explicit", _env_file=None)
    assert settings.ephemeral_secret_key is False
    assert settings.require_secret_key() == "explicit"


def test_weak_or_unsupported_jwt_algorithm_is_rejected():
    for algorithm in ("none", "HS1", "RS256", ""):
        with pytest.raises(Exception):
            Settings(
                environment="test",
                jwt_algorithm=algorithm,
                _env_file=None,
            )
    assert ALLOWED_JWT_ALGORITHMS == {"HS256", "HS384", "HS512"}


def test_expire_minutes_bounds_are_enforced():
    with pytest.raises(Exception):
        Settings(environment="test", jwt_expire_minutes=0, _env_file=None)
    with pytest.raises(Exception):
        Settings(environment="test", jwt_expire_minutes=-1, _env_file=None)


def test_blank_database_url_is_rejected():
    with pytest.raises(Exception):
        Settings(environment="test", database_url="  ", _env_file=None)


def test_secret_key_is_masked_in_repr_and_str():
    settings = Settings(environment="test", secret_key="super-secret", _env_file=None)
    assert "super-secret" not in repr(settings)
    assert "super-secret" not in str(settings)


def test_get_settings_is_cached_and_resettable(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "first")
    first = get_settings()
    assert get_settings() is first
    reset_settings_cache()
    monkeypatch.setenv("SECRET_KEY", "second")
    assert get_settings().secret_key.get_secret_value() == "second"


def test_app_startup_refuses_to_run_without_secret_key():
    from fastapi.testclient import TestClient

    from src.main import app

    with pytest.raises(ConfigurationError):
        with TestClient(app):
            pass


def test_app_starts_in_test_environment(monkeypatch):
    from fastapi.testclient import TestClient

    from src.main import app

    monkeypatch.setenv("ENVIRONMENT", "test")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.app.state.settings.is_test is True
