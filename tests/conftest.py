from __future__ import annotations

from collections.abc import Generator

import pytest
import sqlalchemy
from sqlalchemy.engine import Engine


_ORIGINAL_CREATE_ENGINE = sqlalchemy.create_engine
_CREATED_ENGINES: list[Engine] = []


def _tracked_create_engine(*args, **kwargs) -> Engine:
    """Keep test engines alive until they can be disposed deterministically."""

    engine = _ORIGINAL_CREATE_ENGINE(*args, **kwargs)
    _CREATED_ENGINES.append(engine)
    return engine


# Test modules import create_engine during collection, after this conftest file is
# loaded. Tracking those engines prevents Python 3.14 from finalizing live SQLite
# connections nondeterministically in the middle of another test.
sqlalchemy.create_engine = _tracked_create_engine


@pytest.fixture(autouse=True)
def dispose_test_engines() -> Generator[None, None, None]:
    start_index = len(_CREATED_ENGINES)
    yield

    engines = _CREATED_ENGINES[start_index:]
    for engine in reversed(engines):
        engine.dispose()
    del _CREATED_ENGINES[start_index:]


def pytest_sessionfinish() -> None:
    for engine in reversed(_CREATED_ENGINES):
        engine.dispose()
    _CREATED_ENGINES.clear()
