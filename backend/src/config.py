"""Application settings loaded from the environment.

Every deployment-specific value (signing key, token lifetime, database URL)
comes from the environment. There is deliberately no hard-coded ``SECRET_KEY``
fallback: in any environment other than a test environment a missing, blank,
too-short or placeholder secret aborts startup, because a shipped default key
means every installation signs tokens with the same key.

See ``.env.example`` in the repository root for the variable names. Real
secrets never belong in the repository; ``.gitignore`` excludes ``.env``,
``*.pem`` and friends.
"""

from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic import Field, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Environments in which a missing SECRET_KEY is tolerated. Tests get an
#: ephemeral, per-process key instead; nothing else ever starts without one.
TEST_ENVIRONMENTS = frozenset({"test", "testing"})

#: Shortest signing key accepted. A one-byte key is enough to start a process
#: and useless once an attacker guesses it, so refuse to boot on one. 32
#: characters of ``secrets.token_urlsafe`` entropy is the NIST minimum for a
#: symmetric key (SP 800-57 Part 1 Rev. 5, Table 2).
MIN_SECRET_KEY_LENGTH = 32

#: Values that ship in ``.env.example``. ``cp .env.example .env`` followed by
#: a forgotten edit yields a production instance signing tokens with a key that
#: is published in the repository, which is the same failure mode as shipping a
#: hard-coded default. The app refuses to start on any of them.
PLACEHOLDER_SECRET_KEYS = frozenset({"replace-me-with-a-long-random-value"})

#: Symmetric HMAC algorithms only. "none" and asymmetric algorithms are
#: rejected outright so a caller cannot configure algorithm confusion into the
#: token verification path.
ALLOWED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})

#: Length of the ephemeral key generated for test environments.
_EPHEMERAL_SECRET_BYTES = 48


class ConfigurationError(RuntimeError):
    """Raised when the process is not configured well enough to start.

    Deliberately not a ``ValueError`` subclass: pydantic re-wraps validation
    errors, but lets other exception types through untouched, so the operator
    sees the actionable message instead of a validation traceback.
    """


class Settings(BaseSettings):
    """Process configuration, read from environment variables or ``.env``."""

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
    database_url: str = Field(
        default="postgresql+psycopg://dina@localhost:5432/dina",
    )

    #: True when ``secret_key`` was generated in-process because none was
    #: configured. Never true outside a test environment. A private attribute
    #: rather than a field, so pydantic-settings cannot populate it from an
    #: ``EPHEMERAL_SECRET_KEY`` environment variable: flipping it by hand is
    #: exactly the "we have a key but pretend we do not" state that would let a
    #: deployment start with a meaningless signing key.
    _ephemeral_secret_key: bool = PrivateAttr(default=False)

    @property
    def ephemeral_secret_key(self) -> bool:
        """Whether the signing key was generated in-process for a test run."""
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
            raise ValueError(
                f"unsupported JWT algorithm {algorithm!r}; allowed: {allowed}"
            )
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
                raise ConfigurationError(
                    "SECRET_KEY is the placeholder from .env.example, which is "
                    "published in the repository. Generate a real one with "
                    "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
                    "and set it in the environment. Refusing to start with a "
                    "publicly known signing key."
                )
            if len(configured) < MIN_SECRET_KEY_LENGTH:
                raise ConfigurationError(
                    f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} "
                    f"characters, got {len(configured)}. Generate one with "
                    "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
                    "and set it in the environment. Refusing to start on a "
                    "trivially guessable signing key."
                )
            return self
        if not self.is_test:
            raise ConfigurationError(
                "SECRET_KEY is missing or blank. Generate one with "
                "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
                "and set it in the environment (see .env.example). Refusing "
                "to start without a signing key."
            )
        # Test environments get a random key per process: deterministic tests
        # cannot rely on a shipped secret, and nothing is committed.
        self.secret_key = SecretStr(secrets.token_urlsafe(_EPHEMERAL_SECRET_BYTES))
        self._ephemeral_secret_key = True
        return self

    def require_secret_key(self) -> str:
        """Return the signing key for token issuance and verification."""
        key = self.secret_key.get_secret_value()
        if not key.strip():
            raise ConfigurationError("SECRET_KEY is missing or blank")
        return key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, loading them on first use."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached settings so a later ``get_settings`` re-reads the env."""
    get_settings.cache_clear()
