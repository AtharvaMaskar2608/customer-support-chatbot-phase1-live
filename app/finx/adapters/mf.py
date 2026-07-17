"""MF profile adapter — ``mf.choiceindia.com/api/v2/investor/profile/extended``.

``{Status, Response, Reason}`` envelope; auth is ``authorization: <SSO JWT>`` (the
SSO accessToken, NOT the SessionId). 🔴 HEAVY PII: the ``Response`` object carries
PAN / address / email / mobile / DOB / bank details. The adapter reduces a
successful response to ONLY the first name (from ``FirstHolderName``) at the
transport boundary — the full profile object never becomes the returned payload,
and is never logged, stored, or traced. On any non-success outcome the payload is
discarded entirely (only the server-side ``reason`` is kept). This method's
consumer is Phase-2 (Phase 1 greets by Client ID); it ships transport-complete.
"""

from __future__ import annotations

from app.finx.adapters.base import HttpTransport, endpoint_url, raise_for_auth
from app.finx.adapters.credentials import FinXCredentials
from app.finx.envelopes import Outcome, ParsedEnvelope, parse_dotnet_envelope
from app.finx.models import ENDPOINTS, GetProfileRequest, GetProfileResponse


class MfProfileAdapterImpl:
    """Concrete :class:`~app.finx.interfaces.MfProfileAdapter`."""

    def __init__(self, transport: HttpTransport, credentials: FinXCredentials) -> None:
        self._transport = transport
        self._credentials = credentials

    async def get_profile_extended(self, req: GetProfileRequest) -> ParsedEnvelope:
        spec = ENDPOINTS["profile/extended"]
        status, body = await self._transport.post_json(
            endpoint_url(spec),
            endpoint=spec.name,
            headers={"authorization": self._credentials.sso_jwt or ""},
            json=req.model_dump(),
        )
        env = raise_for_auth(parse_dotnet_envelope(body, http_status=status))
        if env.outcome is Outcome.success:
            profile_obj = env.payload if isinstance(env.payload, dict) else {}
            first_name = GetProfileResponse.model_validate(profile_obj).first_name()
            # Return ONLY the first name; the heavy-PII object is dropped here.
            return ParsedEnvelope(
                outcome=Outcome.success, payload=first_name, reason=env.reason
            )
        # no_data / error: discard any Response payload so no PII can escape.
        return ParsedEnvelope(outcome=env.outcome, payload=None, reason=env.reason)
