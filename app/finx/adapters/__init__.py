"""Concrete per-backend FinX HTTP transport (finx-http-adapters change).

Realizes the frozen ``FinXClient`` interface set (``app/finx/interfaces.py``):
five host/auth/envelope adapters, per-endpoint request assembly, auth-failure and
timeout handling, the server-side byte-fetch + magic-byte/size-floor validation
primitive, and the logging-redaction discipline. No flow logic, no router, no new
contracts — everything here implements already-frozen interfaces.

Public exports are assembled here so callers import from ``app.finx.adapters``.
"""

from __future__ import annotations

from app.finx.adapters.credentials import FinXCredentials
from app.finx.adapters.errors import (
    FinXAuthError,
    FinXError,
    FinXFetchError,
    FinXTimeoutError,
    FinXTransportError,
)

__all__ = [
    "FinXCredentials",
    "FinXError",
    "FinXAuthError",
    "FinXTimeoutError",
    "FinXFetchError",
    "FinXTransportError",
]
