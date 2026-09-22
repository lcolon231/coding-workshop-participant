"""Global test configuration.

Anything here runs before test modules import `acme_core`, which matters: the
settings object is cached and the engine is a module global, so environment
manipulation after import would be silently ignored.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Point every test at a database that is obviously not the developer's. Set
# before any acme_core import so the cached settings can never pick up the real
# local database. Integration tests narrow this further to acme_test_<pid>.
os.environ.setdefault("ACME_PG_NAME", "acme_test_unset")
os.environ.setdefault("ACME_SERVICE_NAME", "auth")
# A stray AWS_LAMBDA_FUNCTION_NAME in the shell would flip the environment
# discriminator and silently add sslmode=require to every test connection.
os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Clear the cached settings around every test.

    `get_settings` is `lru_cache`d, so without this a test that monkeypatches
    the environment would either see a stale object or leak its own into the
    next test.
    """
    from acme_core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
