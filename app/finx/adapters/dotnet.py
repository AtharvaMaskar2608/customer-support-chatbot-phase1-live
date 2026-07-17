""".NET middleware adapter — ``finx.choiceindia.com/api/middleware``.

PascalCase bodies; the ``{Status, Response, Reason}`` envelope; auth is
``authorization: <SessionId>`` header AND ``SessionId`` duplicated in the JSON
body. Owns the three *PDF file endpoints (P&L / Ledger / Tax) and the three
[DATA] fallback endpoints (GetGlobalPNLNew / GetDetailedPNL / GetLedgerDetails).

Every field-level trap lives in the FROZEN request models (``app/finx/models.py``)
— ``LoginId="JIFFY"`` vs ``<client code>``, ``Group`` casing, ``UserId="neuron"``,
``With_Exp`` truthy-for-stable-shape, ``RequestFor`` per endpoint. The adapter
serializes those models verbatim; it never invents a value. The header
``SessionId`` is read from the request model so it always matches the body value.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.finx.adapters.base import HttpTransport, endpoint_url, raise_for_auth
from app.finx.adapters.credentials import FinXCredentials
from app.finx.envelopes import ParsedEnvelope, parse_dotnet_envelope
from app.finx.models import (
    ENDPOINTS,
    EndpointSpec,
    GetDetailedPNLRequest,
    GetGlobalPNLNewRequest,
    GetLedgerDetailsRequest,
    LedgerPdfRequest,
    PnlPdfRequest,
    TaxReportRequest,
)


class DotNetMiddlewareAdapterImpl:
    """Concrete :class:`~app.finx.interfaces.DotNetMiddlewareAdapter`."""

    def __init__(self, transport: HttpTransport, credentials: FinXCredentials) -> None:
        self._transport = transport
        # .NET reads SessionId from the request model (it lives in both header and
        # body and must match); credentials are held for facade-uniform wiring.
        self._credentials = credentials

    async def _call(self, spec: EndpointSpec, req: BaseModel) -> ParsedEnvelope:
        # Every .NET request model carries SessionId; the header must equal it.
        session_id: str = req.SessionId  # type: ignore[attr-defined]
        status, body = await self._transport.post_json(
            endpoint_url(spec),
            endpoint=spec.name,
            headers={"authorization": session_id},
            json=req.model_dump(),
        )
        # HTTP 401 -> FinXAuthError (stale vs garbage SessionId indistinguishable,
        # documented); success/no_data/error returned as a typed envelope.
        return raise_for_auth(parse_dotnet_envelope(body, http_status=status))

    # --- [FILE] delivery endpoints -----------------------------------------

    async def get_global_pnl_pdf(self, req: PnlPdfRequest) -> ParsedEnvelope:
        return await self._call(ENDPOINTS["GetGlobalPNLPDF"], req)

    async def get_ledger_details_pdf(self, req: LedgerPdfRequest) -> ParsedEnvelope:
        return await self._call(ENDPOINTS["GetLedgerDetailsPDF"], req)

    async def get_tax_report_pdf(self, req: TaxReportRequest) -> ParsedEnvelope:
        return await self._call(ENDPOINTS["GetTaxReportPDF"], req)

    # --- [DATA] fallback endpoints (no-data detection / in-chat reads) ------

    async def get_global_pnl_new(self, req: GetGlobalPNLNewRequest) -> ParsedEnvelope:
        return await self._call(ENDPOINTS["GetGlobalPNLNew"], req)

    async def get_detailed_pnl(self, req: GetDetailedPNLRequest) -> ParsedEnvelope:
        return await self._call(ENDPOINTS["GetDetailedPNL"], req)

    async def get_ledger_details(self, req: GetLedgerDetailsRequest) -> ParsedEnvelope:
        return await self._call(ENDPOINTS["GetLedgerDetails"], req)
