"""FinX adapter interfaces (finx-client capability, design D2).

A per-backend adapter SET — NOT one generic wrapper — because casing, envelope
shape, and credential routing all differ per backend. ``app/finx/adapters/**``
(owned by the finx-adapters change) implements these Protocols; a ``FinXClient``
facade Protocol routes each endpoint to the adapter that owns its backend and
forwards the correct credential (SessionId vs SSO JWT) per backend.

This module ships interfaces only. Methods are declared, not implemented.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.finx.envelopes import ParsedEnvelope
from app.finx.models import (
    BrokerageSlabRequest,
    CmlRequest,
    ContractNoteDownloadRequest,
    ContractNoteListRequest,
    GetDetailedPNLRequest,
    GetGlobalPNLNewRequest,
    GetLedgerDetailsRequest,
    GetProfileRequest,
    HoldingsRequest,
    LedgerPdfRequest,
    PnlPdfRequest,
    TaxReportRequest,
)


@runtime_checkable
class DotNetMiddlewareAdapter(Protocol):
    """``finx.choiceindia.com/api/middleware`` — PascalCase; ``{Status, Response,
    Reason}``; auth = ``authorization: <SessionId>`` header AND ``SessionId``
    duplicated in the JSON body. Owns the *PDF file endpoints and the [DATA]
    fallback endpoints."""

    async def get_global_pnl_pdf(self, req: PnlPdfRequest) -> ParsedEnvelope: ...
    async def get_ledger_details_pdf(self, req: LedgerPdfRequest) -> ParsedEnvelope: ...
    async def get_tax_report_pdf(self, req: TaxReportRequest) -> ParsedEnvelope: ...
    async def get_global_pnl_new(self, req: GetGlobalPNLNewRequest) -> ParsedEnvelope: ...
    async def get_detailed_pnl(self, req: GetDetailedPNLRequest) -> ParsedEnvelope: ...
    async def get_ledger_details(self, req: GetLedgerDetailsRequest) -> ParsedEnvelope: ...


@runtime_checkable
class GoMiddlewareAdapter(Protocol):
    """``finx.`` and ``api.choiceindia.com/middleware-go`` — snake_case;
    ``{StatusCode, Message, DevMessage, Body}``; ``authorization`` header only for
    the contract list (``Session ``-prefixed on the ``api.`` per-note download;
    ``get-brokerage-slab`` on ``api.`` uses the SSO JWT). The per-note download
    returns raw PDF bytes, not an envelope."""

    async def list_contract_notes(self, req: ContractNoteListRequest) -> ParsedEnvelope: ...
    async def download_contract_note(self, req: ContractNoteDownloadRequest) -> bytes: ...
    async def get_brokerage_slab(self, req: BrokerageSlabRequest) -> ParsedEnvelope: ...


@runtime_checkable
class MisReportsAdapter(Protocol):
    """``finx.choiceindia.com/mis/reports`` — camelCase; ``{statusCode, message,
    devMessage, body}``; auth = ``authType: jwt`` + ``authorization: <SSO JWT>`` +
    ``source: FINX_ANDROID``. CML fails if handed the SessionId."""

    async def generate_report(self, req: CmlRequest) -> ParsedEnvelope: ...


@runtime_checkable
class MfProfileAdapter(Protocol):
    """``mf.choiceindia.com/api/v2/investor/profile`` — auth = ``authorization:
    <SSO JWT>``. Heavy PII: only the first name is retained."""

    async def get_profile_extended(self, req: GetProfileRequest) -> ParsedEnvelope: ...


@runtime_checkable
class FinxOmneCotiAdapter(Protocol):
    """``finxomne.choiceindia.com/COTI/V1`` — auth = ``authorization: Session
    <SessionId>`` + ``ssotoken: <SSO JWT>`` header + a FINX-issued JWT in the body
    ``accessToken``. Holdings flow is BLOCKED (no file-delivery endpoint)."""

    async def get_holdings(self, req: HoldingsRequest) -> ParsedEnvelope: ...


@runtime_checkable
class FinXClient(Protocol):
    """Facade that routes an endpoint to the adapter that owns its backend and
    forwards the correct credential per backend. Exposes each per-backend adapter;
    the orchestrator calls the facade, not a raw adapter."""

    dotnet: DotNetMiddlewareAdapter
    go: GoMiddlewareAdapter
    mis: MisReportsAdapter
    mf: MfProfileAdapter
    coti: FinxOmneCotiAdapter


#: The five per-backend adapter Protocols (the facade is separate).
ADAPTER_PROTOCOLS: tuple[type, ...] = (
    DotNetMiddlewareAdapter,
    GoMiddlewareAdapter,
    MisReportsAdapter,
    MfProfileAdapter,
    FinxOmneCotiAdapter,
)
