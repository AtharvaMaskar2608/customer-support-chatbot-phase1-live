"""Task 1 — raised transport error taxonomy.

Asserts the four raised types are distinct FinXError/Exception subclasses and
carry only a server-safe ``reason`` (never a URL, credential, or PII).
"""

from __future__ import annotations

from app.finx.adapters.errors import (
    FinXAuthError,
    FinXError,
    FinXFetchError,
    FinXTimeoutError,
    FinXTransportError,
)


def test_all_four_are_distinct_finxerror_subclasses():
    raised = {FinXAuthError, FinXTimeoutError, FinXFetchError, FinXTransportError}
    assert len(raised) == 4
    for cls in raised:
        assert issubclass(cls, FinXError)
        assert issubclass(cls, Exception)


def test_reason_is_carried_for_server_side_logging():
    err = FinXAuthError("auth failed", reason="Invalid SessionId")
    assert err.reason == "Invalid SessionId"


def test_reason_defaults_to_none():
    assert FinXTimeoutError().reason is None
