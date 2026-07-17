"""Router test fixtures + the ``live`` marker deselection.

The ``live`` marker tags the opt-in re-record test that hits the real LLM. Because
``pyproject.toml`` is a frozen surface, the marker is registered here and skipped
by default so the bare ``pytest tests/llm_router/`` command (the testCommand) stays
fully offline. Set ``JINI_RUN_LIVE=1`` to run the live re-record.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

_DIR = Path(__file__).parent


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: opt-in test that calls the real LLM to re-record fixtures (deselected in CI)",
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("JINI_RUN_LIVE"):
        return
    skip_live = pytest.mark.skip(reason="live LLM test; set JINI_RUN_LIVE=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(scope="session")
def recordings_dir() -> Path:
    return _DIR / "recordings"


@pytest.fixture(scope="session")
def goldens_dir() -> Path:
    return _DIR / "goldens"


@pytest.fixture(scope="session")
def recordings(recordings_dir: Path) -> dict:
    return json.loads((recordings_dir / "route_recordings.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def goldens(goldens_dir: Path) -> list:
    return json.loads((goldens_dir / "goldens.json").read_text(encoding="utf-8"))
