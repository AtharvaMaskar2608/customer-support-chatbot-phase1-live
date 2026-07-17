"""Per-session credential bundle forwarded to the FinX adapters.

The frozen adapter Protocol methods (``app/finx/interfaces.py``) take only their
typed ``req`` — they do not carry credentials as parameters. The frozen
``FinXClient`` facade contract mandates that the facade "forwards the correct
credential (SessionId vs SSO JWT) per backend". So credentials are injected at
construction time and read per call:

- ``session_id`` — the FinX ``SessionId``. Used as the ``authorization`` header
  for the ``.NET`` middleware and the Go contract list, and (``Session``-prefixed)
  for the per-note download and COTI. For the ``.NET``/COTI endpoints whose
  request model already carries ``SessionId``, the header MUST match that body
  value; the adapter reads it from the request model there.
- ``sso_jwt`` — the SSO ``accessToken``. Used as the ``authorization`` (or
  ``ssotoken``) header for the JWT-auth backends: MIS (CML), MF (profile),
  brokerage, and the COTI ``ssotoken`` header. ``None`` when the session has no
  SSO token (SessionId-only backends still work).

This object is never logged, serialized to the client, or traced.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FinXCredentials:
    session_id: str
    sso_jwt: str | None = None
