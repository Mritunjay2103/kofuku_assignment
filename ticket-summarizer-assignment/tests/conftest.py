import pytest

import app.main as main


@pytest.fixture(autouse=True)
def _reset_app_state():
    """Isolate tests from shared in-memory cache and rate limiter."""
    main._cache.clear()
    main._limiter.reset()
    yield
    main._cache.clear()
    main._limiter.reset()
