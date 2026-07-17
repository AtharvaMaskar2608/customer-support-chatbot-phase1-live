"""FinX transport-fault seam (blessed byte-fetch split, Wave-1 parallel build).

The byte-fetch primitive ``fetch_report_bytes`` and its typed exceptions are
OWNED by ``finx-http-adapters`` and live in ``app/finx/adapters/`` — a sibling
change that is not yet on main. The engine imports the exception types here so
its retry/error-mapping policy catches exactly the classes the adapters raise.

While ``app.finx.adapters`` is absent (Wave 1), we fall back to local placeholder
classes that match the blessed names. Wave 2 lands the real module and this import
resolves to the real classes with NO engine edit — same names, same package path.

Two deliberate properties:

* The fallback triggers ONLY on ``ModuleNotFoundError`` (the whole package is
  missing), never on a plain ``ImportError``. If the adapters land but forget to
  re-export one of these names, we surface a loud ``ImportError`` instead of
  silently masking the integration break with a placeholder.
* The engine catches the SPECIFIC fault types (never a shared base), so it makes
  no assumption about the adapters' exception hierarchy.
"""

from __future__ import annotations

try:  # Wave 2: the real adapter module is present on main.
    from app.finx.adapters import (  # type: ignore[attr-defined]
        FinXAuthError,
        FinXFetchError,
        FinXTimeoutError,
        FinXTransportError,
    )

    _USING_PLACEHOLDER_FAULTS = False
except ModuleNotFoundError:  # Wave 1: adapters not yet landed — build against fakes.

    class FinXError(Exception):
        """Local base for the placeholder faults (Wave-1 only)."""

    class FinXAuthError(FinXError):
        """HTTP 401 from a FinX backend."""

    class FinXTimeoutError(FinXError):
        """Timeout / network failure fetching from FinX (→ E-TIMEOUT)."""

    class FinXFetchError(FinXError):
        """Report URL fetched but bytes are short / empty / wrong-magic (→ E-FETCH)."""

    class FinXTransportError(FinXError):
        """Unexpected 5xx / parse failure (→ E-UNKNOWN)."""

    _USING_PLACEHOLDER_FAULTS = True


__all__ = [
    "FinXAuthError",
    "FinXFetchError",
    "FinXTimeoutError",
    "FinXTransportError",
]
