"""Application settings loaded from the environment."""

from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic import Field, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TEST_ENVIRONMENTS = frozenset({"test", "testing"})
MIN_SECRET_KEY_LENGTH = 32
PLACEHOLDER_SECRET_KEYS = frozenset({"replace-me-with-a-long-random-value"})
ALLOWED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})
_EPHEMERAL_SECRET_BYTES = 48


class ConfigurationError(RuntimeError):
    """Raised when the process is not configured well enough to start."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="production")
    secret_key: SecretStr = Field(default=SecretStr(""))
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60, ge=1, le=60 * 24 * 30)
    database_url: str = Field(default="postgresql+psycopg://dina@localhost:5432/dina")
    zarinpal_merchant_id: str = Field(default="")
    zarinpal_callback_url: str = Field(default="")
    zarinpal_sandbox: bool = Field(default=False)
    zarinpal_timeout_seconds: float = Field(default=15.0, gt=0, le=60)

    _ephemeral_secret_key: bool = PrivateAttr(default=False)

    @property
    def ephemeral_secret_key(self) -> bool:
        return self._ephemeral_secret_key

    @property
    def is_test(self) -> bool:
        return self.environment.strip().lower() in TEST_ENVIRONMENTS

    @field_validator("environment")
    @classmethod
    def _normalise_environment(cls, value: str) -> str:
        environment = value.strip().lower()
        if not environment:
            raise ValueError("environment must not be blank")
        return environment

    @field_validator("jwt_algorithm")
    @classmethod
    def _check_algorithm(cls, value: str) -> str:
        algorithm = value.strip()
        if algorithm not in ALLOWED_JWT_ALGORITHMS:
            allowed = ", ".join(sorted(ALLOWED_JWT_ALGORITHMS))
            raise ValueError(f"unsupported JWT algorithm {algorithm!r}; allowed: {allowed}")
        return algorithm

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: str) -> str:
        url = value.strip()
        if not url:
            raise ValueError("database_url must not be blank")
        return url

    @model_validator(mode="after")
    def _check_secret_key(self) -> "Settings":
        configured = self.secret_key.get_secret_value().strip()
        if configured:
            if configured in PLACEHOLDER_SECRET_KEYS:
                raise ConfigurationError("SECRET_KEY is the published placeholder; generate a real secret")
            if len(configured) < MIN_SECRET_KEY_LENGTH:
                raise ConfigurationError(
                    f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters"
                )
            return self
        if not self.is_test:
            raise ConfigurationError("SECRET_KEY is missing or blank")
        self.secret_key = SecretStr(secrets.token_urlsafe(_EPHEMERAL_SECRET_BYTES))
        self._ephemeral_secret_key = True
        return self

    def require_secret_key(self) -> str:
        key = self.secret_key.get_secret_value()
        if not key.strip():
            raise ConfigurationError("SECRET_KEY is missing or blank")
        return key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
