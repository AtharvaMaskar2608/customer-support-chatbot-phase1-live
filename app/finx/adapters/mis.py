"""MIS reports adapter — ``finx.choiceindia.com/mis/reports/generate`` (CML).

camelCase body; the ``{statusCode, message, devMessage, body}`` envelope; auth is
three headers at once: ``authType: jwt`` + ``authorization: <SSO JWT>`` +
``source: FINX_ANDROID``. CML fails if handed the ``SessionId`` — it takes the
SSO JWT, never the session id. Success carries the pre-signed link at
``body.cmlLink``, which is fetched server-side (via ``fetch_report_bytes``) and
never surfaced or logged (FLAG B: the 120s single-use signature is not a boundary).
"""

from __future__ import annotations

from app.finx.adapters.base import HttpTransport, endpoint_url, raise_for_auth
from app.finx.adapters.credentials import FinXCredentials
from app.finx.envelopes import ParsedEnvelope, parse_mis_envelope
from app.finx.models import ENDPOINTS, CmlRequest


class MisReportsAdapterImpl:
    """Concrete :class:`~app.finx.interfaces.MisReportsAdapter`."""

    def __init__(self, transport: HttpTransport, credentials: FinXCredentials) -> None:
        self._transport = transport
        self._credentials = credentials

    async def generate_report(self, req: CmlRequest) -> ParsedEnvelope:
        spec = ENDPOINTS["mis/reports/generate"]
        status, body = await self._transport.post_json(
            endpoint_url(spec),
            endpoint=spec.name,
            headers={
                "authType": "jwt",
                "authorization": self._credentials.sso_jwt or "",
                "source": "FINX_ANDROID",
            },
            json=req.model_dump(),
        )
        # HTTP 401 (body {"statusCode":401,...}) -> FinXAuthError; success payload
        # is the body dict carrying cmlLink.
        return raise_for_auth(parse_mis_envelope(body, http_status=status))
