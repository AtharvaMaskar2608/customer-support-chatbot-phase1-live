"""Shared fixture loader for the FinX capture fixtures."""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "finx"


def load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.fixture
def finx_fixture():
    return load
