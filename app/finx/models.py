"""FinX typed request/response models + per-endpoint descriptors (finx-client, 4.3).

Pins the inconsistent-by-design identity fields and enum semantics per endpoint,
matching the 2026-07-16 captures (03_finx_api_reference.md §4/§5). Field names use
each backend's exact casing because these models serialize to FinX. Unverified
values are marked ``[CONFIRM]`` and uncaptured shapes ``[GAP]`` verbatim from the
source doc. Request models forbid extra fields (we control them); response models
tolerate extra fields (the backend may add some).

Security invariants (03 §7): report URLs, ``file_id``, the CML ``cmlLink``, server
filenames, and registered email are sensitive — fetched server-side, never
serialized to the client or logs. ``client_id`` / ``client_code`` are gated by the
authenticated session, never proxied from user input.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Envelope(str, Enum):
    dotnet = "dotnet"  # {Status, Response, Reason}
    go = "go"  # {StatusCode, Message, DevMessage, Body}
    mis = "mis"  # camelCase {statusCode, message, devMessage, body}


class Casing(str, Enum):
    pascal = "pascal"
    snake = "snake"
    camel = "camel"


# ---------------------------------------------------------------------------
# Request models — [FILE] delivery endpoints
# ---------------------------------------------------------------------------


class PnlPdfRequest(BaseModel):
    """GetGlobalPNLPDF (.NET). ``UserId == ClientId``. ``With_Exp`` is a BOOLEAN
    here (the data API GetGlobalPNLNew uses an int). ``RequestFor``: 0=download,
    1=email."""

    model_config = ConfigDict(extra="forbid")

    ClientId: str
    UserId: str  # == ClientId
    Group: str  # Cash (Equity) / Derv (F&O) / Comm (Commodity)
    FromDate: str
    ToDate: str
    RequestFor: int  # 0 = download, 1 = email
    With_Exp: bool = True  # boolean type on the PDF endpoint
    SessionId: str


class LedgerPdfRequest(BaseModel):
    """GetLedgerDetailsPDF (.NET). ``LoginId`` is the CLIENT CODE (not the data
    API's ``"JIFFY"`` literal); ``Group`` is ``"GROUP1"`` UPPERCASE (data API uses
    ``"Group1"``). ``Margin``: 0 = normal ledger; 1 = MTF [CONFIRM] (byte-identical
    on the no-MTF test account). ``RequestFor``: 0 = download; email presumed 1
    [CONFIRM]."""

    model_config = ConfigDict(extra="forbid")

    ClientId: str
    LoginId: str  # client code, NOT "JIFFY"
    Group: str = "GROUP1"  # uppercase
    Margin: int = 0  # 1 = MTF [CONFIRM]
    FromDate: str
    ToDate: str
    RequestFor: int = 0  # email = 1 [CONFIRM]
    SessionId: str


class TaxReportRequest(BaseModel):
    """GetTaxReportPDF (.NET). ``FinYear`` is ``YYYY-YYYY`` (not a date range).
    ``RequestFor``: 2 = download-here, 1 = email. ``FileFormat``: 1 = PDF, 2 =
    Excel. No separate Capital Gain API — CG routes here."""

    model_config = ConfigDict(extra="forbid")

    ClientId: str
    FinYear: str  # "YYYY-YYYY"
    RequestFor: int  # 2 = download, 1 = email
    FileFormat: int  # 1 = PDF, 2 = Excel
    SessionId: str


class CmlRequest(BaseModel):
    """/mis/reports/generate (MIS backend, SSO JWT auth — NOT the SessionId)."""

    model_config = ConfigDict(extra="forbid")

    reportType: str = "cml"
    searchBy: str = "client-id"
    searchValue: str  # client id


class ContractNoteListRequest(BaseModel):
    """/middleware-go/report/contract (Go). snake_case; NO SessionId in body.
    The endpoint enforces no auth (FLAG A) — ``client_id`` MUST be session-gated."""

    model_config = ConfigDict(extra="forbid")

    client_id: str
    from_date: str
    to_date: str


class ContractNoteDownloadRequest(BaseModel):
    """api.choiceindia.com/middleware-go/contract/download (raw PDF bytes back).
    ``client_code`` MUST be session-gated (FLAG A extends here)."""

    model_config = ConfigDict(extra="forbid")

    client_code: str
    file_id: str  # sensitive; server-side only


class BrokerageSlabRequest(BaseModel):
    """api.choiceindia.com/middleware-go/v2/get-brokerage-slab (SSO JWT auth).
    Request key is ``ClientID`` (PascalCase, one word)."""

    model_config = ConfigDict(extra="forbid")

    ClientID: str


class HoldingsRequest(BaseModel):
    """finxomne.choiceindia.com/COTI/V1/Holdings — three credentials at once.
    The body ``accessToken`` is a FINX-issued JWT (iss:FINX), a DIFFERENT token
    from the SSO JWT; its provenance in the widget handoff is unresolved
    [CONFIRM]. Holdings flow is BLOCKED regardless (no file-delivery endpoint)."""

    model_config = ConfigDict(extra="forbid")

    GroupId: str = "HO"
    UserCode: str
    UserId: str
    SessionId: str
    Status: str = ""
    accessToken: str  # FINX-issued JWT [CONFIRM]


class GetProfileRequest(BaseModel):
    """mf.choiceindia.com/api/v2/investor/profile/extended (SSO JWT). HEAVY PII —
    only ``FirstHolderName`` → first name is retained (for the greeting); the rest
    is never logged, stored, traced, or sent to the client."""

    model_config = ConfigDict(extra="forbid")

    InvCode: str


# ---------------------------------------------------------------------------
# Request models — [DATA] fallback endpoints (no-data detection / in-chat reads)
# ---------------------------------------------------------------------------


class GetGlobalPNLNewRequest(BaseModel):
    """GetGlobalPNLNew (data). ``UserId`` = client code. ``With_Exp`` is an INT
    here; ALWAYS send truthy (1) for a stable ``{Trades, Expenses}`` object shape
    (falsy yields a bare array)."""

    model_config = ConfigDict(extra="forbid")

    UserId: str  # client code
    ClientId: str
    Group: str  # Cash / Derv / Comm
    FromDate: str
    ToDate: str
    With_Exp: int = 1  # int; send truthy for stable object shape
    SessionId: str


class GetDetailedPNLRequest(BaseModel):
    """GetDetailedPNL (data). ``UserId`` is the fixed literal ``"neuron"``. This is
    the data side of Global Detail; NO file/download endpoint exists [GAP]."""

    model_config = ConfigDict(extra="forbid")

    UserId: str = "neuron"  # fixed literal
    ClientId: str
    Group: str = "Group1"  # or "Group23"
    FromDate: str
    ToDate: str
    SessionId: str


class GetLedgerDetailsRequest(BaseModel):
    """GetLedgerDetails (data). ``LoginId`` is the literal ``"JIFFY"`` (NOT the
    client code); ``Group`` is ``"Group1"`` (data API casing, vs the PDF endpoint's
    ``"GROUP1"``)."""

    model_config = ConfigDict(extra="forbid")

    LoginId: str = "JIFFY"  # literal, NOT the client code
    ClientId: str
    Group: str = "Group1"
    FromDate: str
    ToDate: str
    SessionId: str


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ContractNote(BaseModel):
    """One contract-note list row (exactly 5 fields). Rows are keyed by
    ``file_id``; ``id`` is redundant (always == ``date``) and MUST NOT be used as a
    key. ``group`` is matched case-insensitively (``Grp1``/``GRP1``). ``date`` is
    ``DDMMYYYY``."""

    date: str  # DDMMYYYY (the trade date)
    file_id: str  # ~88-char opaque token; sensitive, server-side only
    group: str  # only Grp1 seen; match case-insensitively
    id: str  # redundant — always == date; never key by this
    invoice_number: str


class ContractNoteListBody(BaseModel):
    client_code: str
    contractNotes: list[ContractNote] = Field(default_factory=list)

    def by_file_id(self) -> dict[str, ContractNote]:
        """Key rows by ``file_id`` (never ``id``)."""
        return {note.file_id: note for note in self.contractNotes}


class BrokerageRow(BaseModel):
    title: str
    desc: str  # pre-formatted rate text — rendered verbatim, never parsed


class BrokerageGroup(BaseModel):
    title: str
    list: list[BrokerageRow]


class CmlBody(BaseModel):
    cmlLink: str  # AWS SigV4 pre-signed URL; sensitive, fetched server-side & discarded


class GlobalPnlNewObject(BaseModel):
    """GetGlobalPNLNew success shape when ``With_Exp`` is truthy: an object with
    ``Trades`` and ``Expenses``. When ``With_Exp`` is falsy the endpoint returns a
    bare array of trade records instead (no ``Expenses``) — callers MUST check
    whether ``Response`` is an object or an array."""

    Trades: list[dict] = Field(default_factory=list)
    Expenses: list[dict] = Field(default_factory=list)


class FileDeliveryResponse(BaseModel):
    """Polymorphic ``{Status, Response, Reason}`` file-delivery response shared by
    ``GetGlobalPNLPDF``, ``GetLedgerDetailsPDF`` and ``GetTaxReportPDF``.

    ``Response`` is a report URL string on download (the endpoint's download
    ``RequestFor`` value) OR a human-readable confirmation string on email
    (``RequestFor:1``). The email confirmation leaks the full registered email
    (uppercased) — MASK it before any display. The URL is sensitive: fetch
    server-side, never surface or log it.
    """

    model_config = ConfigDict(extra="ignore")

    Status: str
    Response: str | None = None
    Reason: str | None = None

    def is_email_confirmation(self) -> bool:
        return bool(self.Response) and "mail sent" in self.Response.lower()

    def is_download_url(self) -> bool:
        return bool(self.Response) and self.Response.lower().startswith("http")


# Per-endpoint aliases (same polymorphic PascalCase shape).
PnlPdfResponse = FileDeliveryResponse
LedgerPdfResponse = FileDeliveryResponse
TaxReportResponse = FileDeliveryResponse

#: The per-note download returns the raw PDF bytes directly (application/pdf), not
#: a JSON envelope — its "typed model" is the byte string.
ContractNoteDownloadResponse = bytes


class HoldingsResponseBody(BaseModel):
    """Holdings ``Response`` object. ``lDictHoldingData`` is keyed by ISIN (iterate
    ``.values()``), NOT an array. Holdings flow is BLOCKED (no file-delivery
    endpoint); this models the live-data card shape."""

    model_config = ConfigDict(extra="ignore")

    lDictHoldingData: dict[str, dict] = Field(default_factory=dict)  # keyed by ISIN
    BodStatus: int | None = None


class GetProfileResponse(BaseModel):
    """get-profile ``Response`` object. HEAVY PII — retain ONLY the first name from
    ``FirstHolderName``; the full profile must never be logged, stored, traced, or
    returned to the client."""

    model_config = ConfigDict(extra="ignore")

    FirstHolderName: str | None = None

    def first_name(self) -> str | None:
        if not self.FirstHolderName:
            return None
        return self.FirstHolderName.split()[0].title()


class DetailedPnlRow(BaseModel):
    """One ``GetDetailedPNL`` record (data side of Global Detail — no file endpoint
    [GAP])."""

    model_config = ConfigDict(extra="ignore")

    TRADE_DATE: str | None = None
    Scrip_Name: str | None = None
    SECURITY: str | None = None
    Stock: str | None = None
    COMPANY_CODE: str | None = None
    Net_Qty: float | None = None
    Net_Amount: float | None = None


class LedgerDetailsRow(BaseModel):
    """One ``GetLedgerDetails`` record. ``Narration`` may contain third-party PII
    (DP-transfer narrations include another person's name/account) — mask before
    any display."""

    model_config = ConfigDict(extra="ignore")

    trd_Date: str | None = None  # ISO or the 1900-01-01 OPENING sentinel
    vDate: str | None = None  # DD-MM-YYYY
    voucher: str | None = None
    Trans_Type: str | None = None
    Narration: str | None = None  # third-party PII
    Debit: float | None = None
    Credit: float | None = None


# ---------------------------------------------------------------------------
# Per-endpoint descriptors
# ---------------------------------------------------------------------------


class EndpointSpec(BaseModel):
    """Pins a captured endpoint's backend identity, envelope, casing, auth, and
    the per-endpoint enum semantics (RequestFor / FileFormat / identity fields)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    host: str
    path: str
    casing: Casing
    envelope: Envelope
    auth: str
    identity_fields: dict[str, str] = Field(default_factory=dict)
    request_for_download: int | None = None
    request_for_email: int | None = None
    file_format: dict[str, int] | None = None
    blocked: bool = False  # flow has no captured file-delivery endpoint
    confirm: tuple[str, ...] = ()  # [CONFIRM] items, verbatim
    gap: tuple[str, ...] = ()  # [GAP] items, verbatim


ENDPOINTS: dict[str, EndpointSpec] = {
    "GetGlobalPNLPDF": EndpointSpec(
        name="GetGlobalPNLPDF",
        host="finx.choiceindia.com",
        path="/api/middleware/GetGlobalPNLPDF",
        casing=Casing.pascal,
        envelope=Envelope.dotnet,
        auth="authorization: <SessionId> header + SessionId in body",
        identity_fields={"UserId": "<client code> (== ClientId)"},
        request_for_download=0,
        request_for_email=1,
    ),
    "GetLedgerDetailsPDF": EndpointSpec(
        name="GetLedgerDetailsPDF",
        host="finx.choiceindia.com",
        path="/api/middleware/GetLedgerDetailsPDF",
        casing=Casing.pascal,
        envelope=Envelope.dotnet,
        auth="authorization: <SessionId> header + SessionId in body",
        identity_fields={"LoginId": "<client code>", "Group": "GROUP1"},
        request_for_download=0,
        request_for_email=1,
        confirm=(
            "Margin:1 = MTF unverified (byte-identical on the no-MTF test account)",
            "RequestFor:1 email branch untested",
        ),
    ),
    "GetTaxReportPDF": EndpointSpec(
        name="GetTaxReportPDF",
        host="finx.choiceindia.com",
        path="/api/middleware/GetTaxReportPDF",
        casing=Casing.pascal,
        envelope=Envelope.dotnet,
        auth="authorization: <SessionId> header + SessionId in body",
        identity_fields={"FinYear": "YYYY-YYYY"},
        request_for_download=2,  # ViewType-compliant, unlike PNL/Ledger PDF
        request_for_email=1,
        file_format={"pdf": 1, "excel": 2},
    ),
    "report/contract": EndpointSpec(
        name="report/contract",
        host="finx.choiceindia.com",
        path="/middleware-go/report/contract",
        casing=Casing.snake,
        envelope=Envelope.go,
        auth="authorization: <SessionId> header only; NO SessionId in body",
        identity_fields={"client_id": "session-gated (FLAG A: endpoint enforces no auth)"},
    ),
    "contract/download": EndpointSpec(
        name="contract/download",
        host="api.choiceindia.com",
        path="/middleware-go/contract/download",
        casing=Casing.snake,
        envelope=Envelope.go,  # returns raw PDF bytes, not an envelope
        auth="authorization: Session <SessionId>",
        identity_fields={"client_code": "session-gated", "file_id": "sensitive; server-side only"},
        gap=("returns raw PDF bytes (application/pdf), not a JSON envelope",),
    ),
    "get-brokerage-slab": EndpointSpec(
        name="get-brokerage-slab",
        host="api.choiceindia.com",
        path="/middleware-go/v2/get-brokerage-slab",
        casing=Casing.pascal,
        envelope=Envelope.dotnet,  # hybrid envelope, keyed on Status
        auth="authorization: <SSO JWT>",
        identity_fields={"ClientID": "<client id> (PascalCase, one word)"},
    ),
    "mis/reports/generate": EndpointSpec(
        name="mis/reports/generate",
        host="finx.choiceindia.com",
        path="/mis/reports/generate",
        casing=Casing.camel,
        envelope=Envelope.mis,
        auth="authType: jwt + authorization: <SSO JWT> + source: FINX_ANDROID",
        identity_fields={"searchValue": "<client id>"},
    ),
    "Holdings": EndpointSpec(
        name="Holdings",
        host="finxomne.choiceindia.com",
        path="/COTI/V1/Holdings",
        casing=Casing.pascal,
        envelope=Envelope.dotnet,
        auth="authorization: Session <SessionId> + ssotoken: <SSO JWT> + body accessToken: <FINX JWT>",
        identity_fields={"UserCode": "<client code>", "accessToken": "FINX-issued JWT"},
        blocked=True,  # live-data card only; no file-delivery endpoint [GAP]
        confirm=("body accessToken (FINX JWT, iss:FINX) provenance in the widget handoff unresolved",),
        gap=("no file-delivery / PDF endpoint captured — Holding Statement flow BLOCKED",),
    ),
    "profile/extended": EndpointSpec(
        name="profile/extended",
        host="mf.choiceindia.com",
        path="/api/v2/investor/profile/extended",
        casing=Casing.pascal,
        envelope=Envelope.dotnet,
        auth="authorization: <SSO JWT>",
        identity_fields={"InvCode": "<client id>"},
        confirm=("HEAVY PII — retain only FirstHolderName → first name; discard the rest",),
    ),
    "GetGlobalPNLNew": EndpointSpec(
        name="GetGlobalPNLNew",
        host="finx.choiceindia.com",
        path="/api/middleware/GetGlobalPNLNew",
        casing=Casing.pascal,
        envelope=Envelope.dotnet,
        auth="authorization: <SessionId> header + SessionId in body",
        identity_fields={"UserId": "<client code>"},
        confirm=("With_Exp is an int here; truthy → {Trades,Expenses} object, falsy → bare array",),
    ),
    "GetDetailedPNL": EndpointSpec(
        name="GetDetailedPNL",
        host="finx.choiceindia.com",
        path="/api/middleware/GetDetailedPNL",
        casing=Casing.pascal,
        envelope=Envelope.dotnet,
        auth="authorization: <SessionId> header + SessionId in body",
        identity_fields={"UserId": "neuron"},
        blocked=True,  # Global Detail: data only
        gap=("no file/download endpoint exists for Global Detail — flow BLOCKED",),
    ),
    "GetLedgerDetails": EndpointSpec(
        name="GetLedgerDetails",
        host="finx.choiceindia.com",
        path="/api/middleware/GetLedgerDetails",
        casing=Casing.pascal,
        envelope=Envelope.dotnet,
        auth="authorization: <SessionId> header + SessionId in body",
        identity_fields={"LoginId": "JIFFY", "Group": "Group1"},
    ),
}
