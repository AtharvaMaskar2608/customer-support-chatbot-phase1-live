"""Go middleware adapter — ``/middleware-go`` on the ``finx.`` and ``api.`` hosts.

snake_case bodies; the ``{StatusCode, Message, DevMessage, Body}`` envelope for
the contract-note list, but a per-backend mix of auth schemes and response shapes:

- ``list_contract_notes`` — ``finx.`` host, ``authorization: <SessionId>`` header
  ONLY (NO ``SessionId`` in the body). 🔴 FLAG A: the endpoint enforces no auth,
  so ``client_id`` MUST be the session-bound value the caller supplies. The
  adapter never logs it.
- ``download_contract_note`` — ``api.`` host, ``authorization: Session
  <SessionId>`` (the ``"Session "`` prefix). Returns raw ``application/pdf`` bytes
  directly (no envelope), validated through the SAME magic-byte/size-floor
  primitive as ``fetch_report_bytes``. ``file_id`` is sensitive — never logged.
- ``get_brokerage_slab`` — ``api.`` host, SSO-JWT auth, a HYBRID
  ``{StatusCode, Status, Response, Reason}`` envelope parsed via the ``.NET``
  parser (keyed on ``Status``, ignoring the redundant ``StatusCode``). ``desc``
  strings are rendered verbatim downstream; the adapter does not parse rupees.
"""

from __future__ import annotations

from app.contracts.router import ReportFormat
from app.finx.adapters.base import HttpTransport, endpoint_url, raise_for_auth
from app.finx.adapters.credentials import FinXCredentials
from app.finx.adapters.errors import FinXAuthError
from app.finx.adapters.fetch import validate_report_bytes
from app.finx.envelopes import ParsedEnvelope, parse_dotnet_envelope, parse_go_envelope
from app.finx.models import (
    ENDPOINTS,
    BrokerageSlabRequest,
    ContractNoteDownloadRequest,
    ContractNoteListRequest,
)


class GoMiddlewareAdapterImpl:
    """Concrete :class:`~app.finx.interfaces.GoMiddlewareAdapter`."""

    def __init__(self, transport: HttpTransport, credentials: FinXCredentials) -> None:
        self._transport = transport
        self._credentials = credentials

    async def list_contract_notes(self, req: ContractNoteListRequest) -> ParsedEnvelope:
        # authorization: <SessionId> header ONLY; NO SessionId in the body.
        spec = ENDPOINTS["report/contract"]
        status, body = await self._transport.post_json(
            endpoint_url(spec),
            endpoint=spec.name,
            headers={"authorization": self._credentials.session_id},
            json=req.model_dump(),
        )
        # 200 -> success (payload is Body); 204 + Body {} -> no_data.
        return raise_for_auth(parse_go_envelope(body, http_status=status))

    async def download_contract_note(self, req: ContractNoteDownloadRequest) -> bytes:
        # api. host; "Session "-prefixed SessionId; returns raw PDF bytes.
        spec = ENDPOINTS["contract/download"]
        status, data = await self._transport.post_bytes(
            endpoint_url(spec),
            endpoint=spec.name,
            headers={"authorization": f"Session {self._credentials.session_id}"},
            json=req.model_dump(),
        )
        if status == 401:
            raise FinXAuthError("finx auth failed")
        # Same size-floor + magic-byte validation as the URL-fetch delivery path.
        return validate_report_bytes(data, ReportFormat.pdf)

    async def get_brokerage_slab(self, req: BrokerageSlabRequest) -> ParsedEnvelope:
        # api. host; SSO-JWT auth; hybrid envelope parsed via the .NET parser.
        spec = ENDPOINTS["get-brokerage-slab"]
        status, body = await self._transport.post_json(
            endpoint_url(spec),
            endpoint=spec.name,
            headers={"authorization": self._credentials.sso_jwt or ""},
            json=req.model_dump(),
        )
        return raise_for_auth(parse_dotnet_envelope(body, http_status=status))
