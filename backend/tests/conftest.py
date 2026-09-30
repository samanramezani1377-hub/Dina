"""Fixtures shared by the whole backend test suite.

The suite runs as the ``test`` environment. That is the only environment in
which a missing ``SECRET_KEY`` is tolerated: an ephemeral per-process key is
generated instead, so no real secret has to be set, committed or leaked into a
CI log. Everywhere else the app refuses to boot without a strong enough key,
which is exactly the gate the tests that boot the app are meant to exercise.

Setting it here rather than in a CI ``env:`` block keeps the suite
self-contained: ``pytest backend/tests`` works on a laptop with no environment
set up, and the CI job genuinely depends on this fixture instead of on a
variable nothing reads.
"""

import os

import pytest

from src.config import reset_settings_cache


@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """Run the suite as the ``test`` environment with no real signing key."""
    previous_environment = os.environ.get("ENVIRONMENT")
    previous_secret_key = os.environ.get("SECRET_KEY")

    os.environ["ENVIRONMENT"] = "test"
    # A key inherited from the developer's shell or the CI runner must not
    # silently stand in for the ephemeral one, so drop it before the cache is
    # populated.
    os.environ.pop("SECRET_KEY", None)
    reset_settings_cache()

    yield

    for name, value in (
        ("ENVIRONMENT", previous_environment),
        ("SECRET_KEY", previous_secret_key),
    ):
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    reset_settings_cache()


@pytest.fixture(scope="session")
def client():
    """A ``TestClient`` that has entered the context manager.

    ``TestClient(app)`` alone never starts the ASGI lifespan: Starlette only
    runs it on ``__enter__``. A client built that way skips the fail-fast
    settings gate in :func:`src.main.lifespan` entirely, which is how a test
    suite ends up green against a deployment path that crashes on boot.
    """
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as test_client:
        yield test_client
