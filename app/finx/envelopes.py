"""FinX response-envelope parsers (finx-client capability, design D3).

Exactly THREE pure parsers, each normalizing a backend's envelope into a
``ParsedEnvelope{outcome, payload, reason}``. Never build one generic parser
(two-parsers-minimum is a hard rule).

Auth failure is detected by the transport HTTP status (401), before envelope
parsing, because auth failures do not follow the in-band 200-with-Fail
convention and the two 401 bodies (.NET vs MIS) differ. All other outcomes are
branched on the body envelope, never on HTTP status.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class Outcome(str, Enum):
    success = "success"
    no_data = "no_data"
    auth_error = "auth_error"
    error = "error"


class ParsedEnvelope(BaseModel):
    """A backend response normalized across all three envelope shapes."""

    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    payload: Any = None  # the polymorphic Response / Body
    reason: str | None = None  # server-provided reason (logged server-side only)


#: No-data is reason-SET based, never a single literal — wording differs per
#: endpoint ("Data not found." vs "Data not available.").
NO_DATA_REASONS: frozenset[str] = frozenset({"Data not found.", "Data not available."})


def _is_auth_401(http_status: int | None) -> bool:
    return http_status == 401


def parse_dotnet_envelope(body: dict[str, Any], *, http_status: int | None = None) -> ParsedEnvelope:
    """Parse the PascalCase ``{Status, Response, Reason}`` envelope.

    Serves the legacy `.NET` middleware, the `mf.` profile, COTI Holdings, AND the
    brokerage hybrid envelope: it tolerates extra keys (ignores a redundant
    ``StatusCode``) and keys on ``Status``. ``Response`` is polymorphic — URL
    string, confirmation string, array, object, null, or empty string (the `.NET`
    401 auth body uses ``Response: ""``).
    """
    if _is_auth_401(http_status):
        return ParsedEnvelope(outcome=Outcome.auth_error, reason=body.get("Reason"))

    status = body.get("Status")
    reason = body.get("Reason")
    if status == "Success":
        return ParsedEnvelope(outcome=Outcome.success, payload=body.get("Response"), reason=reason)
    if status == "Fail":
        if reason in NO_DATA_REASONS:
            return ParsedEnvelope(outcome=Outcome.no_data, payload=body.get("Response"), reason=reason)
        return ParsedEnvelope(outcome=Outcome.error, payload=body.get("Response"), reason=reason)
    return ParsedEnvelope(outcome=Outcome.error, payload=body.get("Response"), reason=reason)


def parse_go_envelope(body: dict[str, Any], *, http_status: int | None = None) -> ParsedEnvelope:
    """Parse the Go middleware ``{StatusCode, Message, DevMessage, Body}`` envelope.

    Success: ``StatusCode == 200``. No-data: ``StatusCode == 204`` with
    ``Body == {}``.
    """
    if _is_auth_401(http_status):
        return ParsedEnvelope(outcome=Outcome.auth_error, reason=body.get("Message"))

    status_code = body.get("StatusCode")
    reason = body.get("Message")
    payload = body.get("Body")
    if status_code == 200:
        return ParsedEnvelope(outcome=Outcome.success, payload=payload, reason=reason)
    if status_code == 204 and payload == {}:
        return ParsedEnvelope(outcome=Outcome.no_data, payload=payload, reason=reason)
    return ParsedEnvelope(outcome=Outcome.error, payload=payload, reason=reason)


def parse_mis_envelope(body: dict[str, Any], *, http_status: int | None = None) -> ParsedEnvelope:
    """Parse the MIS camelCase ``{statusCode, message, devMessage, body}`` envelope
    (CML). Success: ``statusCode == 200``. The auth-failure body is
    ``{"statusCode":401,...}`` but detection is by HTTP 401."""
    if _is_auth_401(http_status):
        return ParsedEnvelope(outcome=Outcome.auth_error, reason=body.get("message"))

    status_code = body.get("statusCode")
    reason = body.get("message")
    payload = body.get("body")
    if status_code == 200:
        return ParsedEnvelope(outcome=Outcome.success, payload=payload, reason=reason)
    if status_code == 401:
        return ParsedEnvelope(outcome=Outcome.auth_error, payload=payload, reason=reason)
    return ParsedEnvelope(outcome=Outcome.error, payload=payload, reason=reason)
