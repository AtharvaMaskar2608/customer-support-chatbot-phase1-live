"""Shared fixtures for the ticketing test suite.

Fully offline: a hermetic config (no real secret), a fixed SessionContext, a
recorded-fixture loader, and a client pointed at the test base URL. All Freshdesk
HTTP is mocked with respx in the individual tests — no live calls.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.contracts.wire import SessionContext
from app.ticketing.client import FreshdeskClient
from app.ticketing.config import load_config
from app.ticketing.tool import reset_idempotency_cache

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"

#: The test Freshdesk base URL (no trailing slash, matching config normalization).
ROOT = "https://choicebroking.freshdesk.com/api/v2"


def load(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def fd_fixture():
    return load


@pytest.fixture
def config():
    """Hermetic config: env supplied inline, no real FRESHDESK_API_KEY needed."""
    return load_config(env={"FRESHDESK_API_KEY": "testkey", "FRESHDESK_API_ROOT": ROOT})


@pytest.fixture
def session():
    return SessionContext(
        user_id="X008593",
        session_id="SESSION-SECRET",
        access_token="JWT-SECRET",
        platform="web",
        page="support",
        entry_surface="support",
    )


@pytest.fixture
def client():
    return FreshdeskClient(ROOT, "testkey")


@pytest.fixture(autouse=True)
def _reset_idem():
    """The idempotency guard is module-level; reset it around every test."""
    reset_idempotency_cache()
    yield
    reset_idempotency_cache()
