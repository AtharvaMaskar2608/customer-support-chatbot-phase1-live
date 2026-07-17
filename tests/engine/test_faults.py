"""T1: the FinX transport-fault seam (blessed byte-fetch split, Wave-1 build).

Asserts what the proposal's integration seam requires: the engine imports the
adapter-owned fault types by their blessed names, falls back to placeholders only
while ``app.finx.adapters`` is absent, and exposes catchable, distinct exception
classes for the retry / error-mapping policy.
"""

from __future__ import annotations

import importlib.util

from app.engine import faults


def test_fault_types_are_distinct_catchable_exceptions():
    for exc in (
        faults.FinXFetchError,
        faults.FinXTimeoutError,
        faults.FinXAuthError,
        faults.FinXTransportError,
    ):
        assert issubclass(exc, Exception)

    # Distinct classes — the engine catches specific types, never a shared base.
    names = {
        faults.FinXFetchError,
        faults.FinXTimeoutError,
        faults.FinXAuthError,
        faults.FinXTransportError,
    }
    assert len(names) == 4

    # A raised fetch fault is caught by its specific type but NOT by timeout.
    try:
        raise faults.FinXFetchError("bad bytes")
    except faults.FinXTimeoutError:  # pragma: no cover
        raise AssertionError("FinXFetchError must not be a FinXTimeoutError")
    except faults.FinXFetchError as exc:
        assert str(exc) == "bad bytes"


def test_placeholder_only_while_adapters_absent():
    adapters_present = importlib.util.find_spec("app.finx.adapters") is not None
    # Placeholders are in use IFF the real adapter package is not on main yet.
    assert faults._USING_PLACEHOLDER_FAULTS == (not adapters_present)


def test_blessed_names_are_exported():
    assert set(faults.__all__) == {
        "FinXAuthError",
        "FinXFetchError",
        "FinXTimeoutError",
        "FinXTransportError",
    }
