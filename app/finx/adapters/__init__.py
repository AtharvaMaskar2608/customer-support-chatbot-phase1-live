"""Concrete per-backend FinX HTTP transport (finx-http-adapters change).

Realizes the frozen ``FinXClient`` interface set (``app/finx/interfaces.py``):
five host/auth/envelope adapters, per-endpoint request assembly, auth-failure and
timeout handling, the server-side byte-fetch + magic-byte/size-floor validation
primitive, and the logging-redaction discipline. No flow logic, no router, no new
contracts — everything here implements already-frozen interfaces.

Public exports are assembled here so callers import from ``app.finx.adapters``.
"""

from __future__ import annotations

from app.finx.adapters.base import HttpTransport, TransportSettings
from app.finx.adapters.coti import FinxOmneCotiAdapterImpl
from app.finx.adapters.credentials import FinXCredentials
from app.finx.adapters.dotnet import DotNetMiddlewareAdapterImpl
from app.finx.adapters.errors import (
    FinXAuthError,
    FinXError,
    FinXFetchError,
    FinXTimeoutError,
    FinXTransportError,
)
from app.finx.adapters.facade import FinXClientImpl
from app.finx.adapters.fetch import fetch_report_bytes, validate_report_bytes
from app.finx.adapters.go import GoMiddlewareAdapterImpl
from app.finx.adapters.mf import MfProfileAdapterImpl
from app.finx.adapters.mis import MisReportsAdapterImpl

__all__ = [
    # facade + credentials + transport
    "FinXClientImpl",
    "FinXCredentials",
    "HttpTransport",
    "TransportSettings",
    # the five per-backend adapters
    "DotNetMiddlewareAdapterImpl",
    "GoMiddlewareAdapterImpl",
    "MisReportsAdapterImpl",
    "MfProfileAdapterImpl",
    "FinxOmneCotiAdapterImpl",
    # byte-fetch + validation primitive
    "fetch_report_bytes",
    "validate_report_bytes",
    # raised transport errors
    "FinXError",
    "FinXAuthError",
    "FinXTimeoutError",
    "FinXFetchError",
    "FinXTransportError",
]
