"""COTI (finxomne) holdings adapter — ``finxomne.choiceindia.com/COTI/V1/Holdings``.

``{Status, Response, Reason}`` envelope; THREE credentials at once:
``authorization: Session <SessionId>`` + ``ssotoken: <SSO JWT>`` headers, plus a
FINX-issued JWT as the body ``accessToken``. The ``SessionId`` is read from the
request model (it lives in the body too and must match the header); the SSO JWT
is the forwarded credential; the FINX JWT is CALLER-SUPPLIED via
``HoldingsRequest.accessToken`` — its provenance in the widget handoff is
unresolved [CONFIRM], so the adapter takes it as given and never sources it.

The Holdings flow is BLOCKED (no captured file-delivery endpoint), but the
transport is complete here. ``SessionId`` and both JWTs are never logged.
"""

from __future__ import annotations

from app.finx.adapters.base import HttpTransport, endpoint_url, raise_for_auth
from app.finx.adapters.credentials import FinXCredentials
from app.finx.envelopes import ParsedEnvelope, parse_dotnet_envelope
from app.finx.models import ENDPOINTS, HoldingsRequest


class FinxOmneCotiAdapterImpl:
    """Concrete :class:`~app.finx.interfaces.FinxOmneCotiAdapter`."""

    def __init__(self, transport: HttpTransport, credentials: FinXCredentials) -> None:
        self._transport = transport
        self._credentials = credentials

    async def get_holdings(self, req: HoldingsRequest) -> ParsedEnvelope:
        spec = ENDPOINTS["Holdings"]
        status, body = await self._transport.post_json(
            endpoint_url(spec),
            endpoint=spec.name,
            headers={
                # Session-prefixed SessionId (matches the body value) + SSO JWT.
                "authorization": f"Session {req.SessionId}",
                "ssotoken": self._credentials.sso_jwt or "",
            },
            # Body carries GroupId=HO, UserCode, UserId, SessionId, Status, and the
            # caller-supplied FINX-issued accessToken.
            json=req.model_dump(),
        )
        return raise_for_auth(parse_dotnet_envelope(body, http_status=status))
