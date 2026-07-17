"""PII masking for trace data (tracing-observability capability).

``mask_pii`` is the concrete implementation of the frozen ``MaskFn`` hook
(``app/contracts/tracing.py``). DeepEval applies it to every span input/output
before the data is serialized/exported, so no name, email, Client ID, PAN,
ledger amount, or phone number ever leaves the process.

Two layers, applied together while recursing ``dict``/``list``/``str``:

1. **Key-based** — any mapping key matching the frozen ``PII_KEYS`` list
   (names, emails, Client IDs, ledger debit/credit, session credentials, …)
   has its whole value redacted to ``***``. This reuses the exact key list the
   contract froze (substring, case-insensitive), so key coverage never drifts
   from ``default_mask``.
2. **Value-based** — PII embedded *inside* string values (where no key marks
   it, e.g. a "mail sent to …" confirmation string, or a Client ID/PAN pasted
   into free text) is redacted by regex to a typed token.

The value tokens are intentionally typed (``[EMAIL_REDACTED]`` etc.) so a
redacted trace still shows *what class* of PII was present without revealing it.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.contracts.tracing import PII_KEYS

#: Whole-value redaction marker for PII-keyed fields (matches the frozen
#: ``default_mask`` precedent in ``app/contracts/tracing.py``).
KEY_REDACTED = "***"

# --- Value-level patterns (redact PII embedded inside string values) ---------

#: Email addresses, including the app's already-masked form
#: ``san***.harsha@gmail.com`` (``*`` is allowed in the local part) and
#: uppercased leaks inside confirmation strings.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+*-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

#: PAN — five letters, four digits, one letter (the PDF password; must never
#: be traced). Matched anywhere in a string.
_PAN_RE = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")

#: FinX Client ID / code (e.g. ``X008593``). Anchored to the whole string, per
#: the proposal — a bare string value that *is* a Client ID. Client IDs carried
#: under a PII key are already redacted by the key layer.
_CLIENT_ID_RE = re.compile(r"^[A-Za-z]\d{5,6}$")

#: Phone numbers — 10 digits, optionally with a ``+91`` country prefix.
_PHONE_RE = re.compile(r"(?<!\d)(?:\+91[-\s]?)?\d{10}(?!\d)")

#: Ledger / currency amounts embedded in strings: a ``₹``-prefixed number, or a
#: number written with a 2-decimal (currency) fraction and optional thousands
#: separators. Plain integers, single-decimal floats, and ISO dates are left
#: alone so non-PII stays intact.
_AMOUNT_RE = re.compile(r"₹\s?[\d,]+(?:\.\d+)?|(?<!\d)\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|(?<!\d)\d+\.\d{2}(?!\d)")


def _is_pii_key(key: Any) -> bool:
    return isinstance(key, str) and any(p in key.lower() for p in PII_KEYS)


def _mask_string(value: str) -> str:
    """Redact PII embedded inside a single string value.

    Order matters: emails first (they contain no digit runs the later patterns
    care about), then PAN, then the anchored Client-ID whole-value case, then
    phones, then amounts. The typed tokens themselves contain no digits, so no
    substitution can cascade into another.
    """
    value = _EMAIL_RE.sub("[EMAIL_REDACTED]", value)
    value = _PAN_RE.sub("[PAN]", value)
    value = _CLIENT_ID_RE.sub("[CLIENT_ID]", value)
    value = _PHONE_RE.sub("[PHONE]", value)
    value = _AMOUNT_RE.sub("[AMOUNT]", value)
    return value


def mask_pii(data: Any) -> Any:
    """Recursively redact PII in trace data before export (the frozen ``mask``
    hook). Key-based redaction for PII-keyed mapping values; value-based regex
    redaction for PII embedded inside strings. Non-PII values pass through
    unchanged."""
    if isinstance(data, Mapping):
        masked: dict[Any, Any] = {}
        for key, value in data.items():
            masked[key] = KEY_REDACTED if _is_pii_key(key) else mask_pii(value)
        return masked
    if isinstance(data, (list, tuple)):
        redacted = [mask_pii(item) for item in data]
        return type(data)(redacted) if isinstance(data, tuple) else redacted
    if isinstance(data, str):
        return _mask_string(data)
    return data
