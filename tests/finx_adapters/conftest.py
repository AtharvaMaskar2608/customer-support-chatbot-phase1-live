"""Shared fixtures for the FinX adapter tests.

All tests are offline: httpx is mocked with ``respx`` and response bodies come
from the ``tests/fixtures/finx/**`` captures declared by ``contracts-foundation``.
No live FinX calls, ever.
"""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Callable

import httpx
import pytest

from app.finx.adapters.base import HttpTransport
from app.finx.adapters.credentials import FinXCredentials

FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "finx"


def load_fixture(name: str) -> dict:
    """Load a capture fixture by bare name (``.json`` appended if absent)."""
    if not name.endswith(".json"):
        name = f"{name}.json"
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.fixture
def finx_fixture() -> Callable[[str], dict]:
    return load_fixture


@pytest.fixture
def credentials() -> FinXCredentials:
    return FinXCredentials(session_id="SESS-TEST-0001", sso_jwt="jwt.sso.token")


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


@pytest.fixture
async def transport(client):
    return HttpTransport(client)


@pytest.fixture
def log_capture():
    """Capture everything logged under ``app.finx.adapters`` for redaction asserts.

    Returns a callable giving the concatenated formatted log text so tests can
    assert that no secret substring ever reached a sink.
    """
    records: list[logging.LogRecord] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Handler()
    logger = logging.getLogger("app.finx.adapters")
    prior_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield lambda: "\n".join(handler.format(r) for r in records)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior_level)
