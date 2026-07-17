"""Raised transport errors for the FinX adapters (finx-http-adapters change).

The adapters distinguish *in-band business failures* from *transport failures*:

- Business failures arrive as HTTP 200 with an envelope ``Status``/``StatusCode``
  and are returned as a typed :class:`~app.finx.envelopes.ParsedEnvelope`
  (``no_data`` / ``error``) — NEVER raised.
- Transport failures are raised as the four types below. The engine
  (``flow-engine-runtime``) maps them to the shared error taxonomy
  (``E-TIMEOUT`` / ``E-FETCH`` / ``E-UNKNOWN``).

The raised types intentionally carry only the server-provided ``reason`` (safe
for the server-side log) — never a URL, ``file_id``, ``SessionId``, JWT, or PII.
"""

from __future__ import annotations


class FinXError(Exception):
    """Base for every raised FinX transport error.

    ``reason`` is the server-provided diagnostic string (logged server-side
    only). It must never be a report URL, ``file_id``, credential, or PII.
    """

    def __init__(self, message: str = "", *, reason: str | None = None) -> None:
        super().__init__(message or reason or self.__class__.__name__)
        self.reason = reason


class FinXAuthError(FinXError):
    """HTTP 401 from any backend. Stale vs garbage ``SessionId`` are
    indistinguishable at this layer (documented, not a bug)."""


class FinXTimeoutError(FinXError):
    """Connect/read timeout or a network failure (DNS, connection reset) that
    survived the single bounded retry. Mapped to ``E-TIMEOUT`` downstream."""


class FinXFetchError(FinXError):
    """Server-side byte fetch or validation failure — short/empty/wrong-magic
    bytes, or a non-200 on the report URL. Mapped to ``E-FETCH`` downstream."""


class FinXTransportError(FinXError):
    """Unexpected transport outcome — a persistent 5xx after retry, or a body
    that could not be parsed as the expected envelope. Mapped to ``E-UNKNOWN``."""
