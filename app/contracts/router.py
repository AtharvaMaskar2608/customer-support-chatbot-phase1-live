"""Router I/O contract (router-contract capability).

The complete, frozen router input/output surface: the 16-value ``Intent`` enum,
``Segment`` / ``ReportFormat`` / ``Delivery`` enums, ``ExtractedParams``,
``ConversationContext``, ``RouterResult``, the deterministic intent-precedence
constants, and the raise-ticket / ticket-status tool request/result types.

Downstream changes consume these types and are forbidden from adding, removing,
or renaming ``Intent`` values or editing this module (CLAUDE.md frozen surface).
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Intent(str, Enum):
    """Every intent the router can classify an utterance into (frozen: exactly 16).

    Eleven report-flow intents + five non-report intents. ``report_holding`` and
    ``report_global_detail`` are classifiable but BLOCKED (no captured
    file-delivery endpoint) — the orchestrator returns a not-yet-available
    message rather than attempting fulfilment.
    """

    # --- 11 report intents ---
    report_pnl = "report_pnl"  # P&L Statement (GetGlobalPNLPDF)
    report_ledger = "report_ledger"  # Ledger (GetLedgerDetailsPDF, Margin:0)
    report_mtf_ledger = "report_mtf_ledger"  # MTF Ledger (GetLedgerDetailsPDF, Margin:1 [CONFIRM])
    report_contract_notes = "report_contract_notes"  # Contract Notes (list + per-note download)
    report_tax = "report_tax"  # Tax Report (GetTaxReportPDF)
    report_capital_gain = "report_capital_gain"  # routes to Tax flow; CG education line
    report_tax_pnl = "report_tax_pnl"  # routes to Tax flow; Tax-P&L education line
    report_cml = "report_cml"  # CML (/mis/reports/generate)
    report_brokerage = "report_brokerage"  # Brokerage slab card (get-brokerage-slab)
    report_holding = "report_holding"  # BLOCKED: no captured file-delivery endpoint
    report_global_detail = "report_global_detail"  # BLOCKED: no captured file-delivery endpoint

    # --- 5 non-report intents ---
    rag_qa = "rag_qa"
    raise_ticket = "raise_ticket"
    ticket_status = "ticket_status"
    call_support = "call_support"
    smalltalk_fallback = "smalltalk_fallback"


class Segment(str, Enum):
    """Customer-facing segment. The Segment→API group mapping (Cash/Derv/Comm,
    Grp1/MCX) lives in the FinX layer, NOT in the router contract."""

    equity = "equity"
    fno = "fno"
    commodity = "commodity"


class ReportFormat(str, Enum):
    pdf = "pdf"
    excel = "excel"


class Delivery(str, Enum):
    """In-chat delivery vs email."""

    in_chat = "in_chat"
    email = "email"


class Language(str, Enum):
    """Detected conversation language for the sticky-language rule."""

    english = "english"
    hindi = "hindi"
    hinglish = "hinglish"


class DateRange(BaseModel):
    """A ``from``/``to`` date range lifted from an utterance."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    from_: date | None = Field(default=None, alias="from")
    to: date | None = None


class ExtractedParams(BaseModel):
    """Parameters the router lifts from free text. Every field is optional — the
    flow engine collects the rest via stepper chips."""

    model_config = ConfigDict(extra="forbid")

    fy: str | None = None
    date_range: DateRange | None = None
    segment: Segment | None = None
    report_format: ReportFormat | None = None
    delivery: Delivery | None = None


class TurnRef(BaseModel):
    """A reference to a prior turn in the conversation history."""

    model_config = ConfigDict(extra="forbid")

    turn_id: str
    turn_number: int


class ConversationContext(BaseModel):
    """Frozen input to the router and the orchestrator pipeline.

    ``session_id`` and ``access_token`` are retained (different FinX backends need
    different credentials) but excluded from serialization — they SHALL NOT reach
    the client.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str
    session_id: str = Field(exclude=True)
    access_token: str = Field(exclude=True)
    is_dark_theme: bool = False
    platform: str
    page: str
    history: list[TurnRef] = Field(default_factory=list)
    turn_number: int = 0
    follow_up_count: int = 0
    detected_language: Language | None = None
    language_locked: bool = False


class RouterResult(BaseModel):
    """The router's complete, frozen output.

    Materialized directly from the API-validated ``route`` tool ``tool_use.input``;
    the deterministic post-layers (precedence, FY computation, sticky-language)
    run on this result.
    """

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    extracted_params: ExtractedParams = Field(default_factory=ExtractedParams)
    needs_confirmation: bool = False  # AY→FY case requiring explicit confirmation
    follow_up_question: str | None = None  # disambiguation prompt, only when genuinely ambiguous
    detected_language: Language | None = None
    escalate: bool = False  # true at the follow-up cap → route to ticket/call
    education_line: str | None = None  # CG / Tax-P&L education prefix


# --- Raise-ticket / ticket-status tool request/result types ---
# The Freshdesk field mapping used to build the ticket is ticketing-owned config
# (app/ticketing/freshdesk.yaml), NOT part of these contract types.


class RaiseTicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str
    query_type: str
    transcript_ref: str  # reference to the conversation transcript


class RaiseTicketResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    status: str


class TicketStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_ref: str


class TicketStatusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    status: str


# --- Deterministic classification constants ---

#: Classifiable but not fulfillable — no captured file-delivery endpoint.
BLOCKED_INTENTS: frozenset[Intent] = frozenset(
    {Intent.report_holding, Intent.report_global_detail}
)

#: Intents fulfilled by the Tax Report flow (there is no separate Capital Gain API).
TAX_FLOW_INTENTS: frozenset[Intent] = frozenset(
    {Intent.report_tax, Intent.report_capital_gain, Intent.report_tax_pnl}
)

#: Intents that carry an education-line prefix.
EDUCATION_LINE_INTENTS: frozenset[Intent] = frozenset(
    {Intent.report_capital_gain, Intent.report_tax_pnl}
)

#: Deterministic intent precedence for ambiguous utterances, highest-precedence
#: first. ``tax`` anywhere beats ``p&l``/``pnl``; ``capital gain``/``cg`` means the
#: Tax Report; ``holding statement`` resolves to holding (not ledger); bare
#: ``p&l``/``pnl`` resolves to report_pnl. The first token found in an utterance wins.
PRECEDENCE_TOKENS: tuple[tuple[str, Intent], ...] = (
    ("tax", Intent.report_tax),
    ("capital gain", Intent.report_capital_gain),
    ("cg", Intent.report_capital_gain),
    ("holding statement", Intent.report_holding),
    ("ledger", Intent.report_ledger),
    ("account statement", Intent.report_ledger),
    ("contract note", Intent.report_contract_notes),
    ("brokerage", Intent.report_brokerage),
    ("cml", Intent.report_cml),
    ("p&l", Intent.report_pnl),
    ("pnl", Intent.report_pnl),
)
