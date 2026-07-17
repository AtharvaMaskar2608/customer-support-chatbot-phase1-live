"""Widget ↔ backend wire contract (chat-wire-api capability).

The complete HTTP contract between the React widget and the FastAPI backend:
``SessionContext`` (session bootstrap from URL params), the non-streaming
``POST /api/chat`` request/response envelope, the discriminated render-block
union (11 block types the widget can display), the chip-action contract, and the
session-seed ``config_slice``.

Design decisions (see design.md): D1 non-streaming one-response-per-turn; D10
config reaches the widget only inside the first chat response; D11 the render
union has a checked-in generated JSON Schema with a drift test.

Serialization rule: the wire is snake_case throughout (matching the spec), with
the single deliberate exception of the note-list ``downloadToken`` field, which
serializes camelCase via alias. Serialize the wire with ``by_alias=True`` so that
one exception renders correctly and everything else is unchanged.
"""

from __future__ import annotations

import json
from datetime import date
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.contracts.errors import ErrorCode
from app.contracts.router import DateRange, Intent

# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------


class EntrySurface(str, Enum):
    support = "support"
    reports = "reports"


def _to_bool(value: bool | str | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "dark"}


class SessionContext(BaseModel):
    """Typed session context derived from the app-handoff URL query params.

    ``session_id`` and ``access_token`` are both retained (different FinX
    backends require different credentials) but are excluded from serialization —
    they SHALL NOT be echoed to the widget in any response body or render block.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str  # Client ID, e.g. X008593
    session_id: str = Field(exclude=True)
    access_token: str = Field(exclude=True)  # SSO JWT
    is_dark_theme: bool = False
    platform: str
    page: str
    entry_surface: EntrySurface

    @classmethod
    def from_url_params(
        cls,
        *,
        userId: str,
        sessionId: str,
        accessToken: str,
        isDarkTheme: bool | str | None = False,
        platform: str,
        page: str,
    ) -> "SessionContext":
        """Build a SessionContext from the six app-handoff URL params, resolving
        the entry surface from ``page`` (reports screen → reports, else support)."""
        surface = (
            EntrySurface.reports if "report" in page.lower() else EntrySurface.support
        )
        return cls(
            user_id=userId,
            session_id=sessionId,
            access_token=accessToken,
            is_dark_theme=_to_bool(isDarkTheme),
            platform=platform,
            page=page,
            entry_surface=surface,
        )


# ---------------------------------------------------------------------------
# Chip action contract
# ---------------------------------------------------------------------------


class ChipActionKind(str, Enum):
    """The typed chip-action set. A chip action is sufficient for the backend to
    advance a flow deterministically, without free-text parsing."""

    send_text = "send_text"
    select_param = "select_param"  # segment / FY / format / delivery selection
    open_calendar = "open_calendar"
    raise_ticket = "raise_ticket"
    call_support = "call_support"
    retry = "retry"
    email = "email"
    show_more = "show_more"  # pagination
    deep_link = "deep_link"  # prefilled prompt


class ChipAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ChipActionKind
    payload: dict[str, str] = Field(default_factory=dict)


class Chip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    action: ChipAction


# ---------------------------------------------------------------------------
# Render-block union (discriminated on `type`)
# ---------------------------------------------------------------------------


class Bubble(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["bubble"] = "bubble"
    text: str
    compliance_footer: bool = False


class UserBubble(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["user_bubble"] = "user_bubble"
    text: str


class ChipRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["chip_row"] = "chip_row"
    chips: list[Chip]


class StepState(str, Enum):
    pending = "pending"
    active = "active"
    done = "done"


class StepperStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    state: StepState
    selected_label: str | None = None
    chips: list[Chip] = Field(default_factory=list)


class StepperCard(BaseModel):
    """Editable multi-step card. Completed steps stay tappable: reopening a done
    step clears downstream selections; the prior file card stays in history and
    nothing is re-fetched until generation."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["stepper_card"] = "stepper_card"
    steps: list[StepperStep]


class Calendar(BaseModel):
    """In-chat date picker. Out-of-range dates are hard-disabled (the engine
    disables them rather than validating after selection)."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["calendar"] = "calendar"
    min_date: date
    max_date: date
    disabled_ranges: list[DateRange] = Field(default_factory=list)
    max_range_days: int | None = None


class FileCard(BaseModel):
    """A delivered report file. Carries only display-safe fields — NO report URL,
    file_id, cmlLink, or server filename. For CML the display filename is the
    server's own ``Client_Master_List.pdf``; for every other flow it is renamed so
    it does not leak the Client ID."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["file_card"] = "file_card"
    filename: str  # display filename only
    size_label: str  # e.g. "182 KB"
    format: Literal["pdf", "xlsx"]
    password_hint: str | None = None  # e.g. "PAN"
    helper: str = "Trouble opening it? Tell me."
    actions: list[Chip] = Field(default_factory=list)  # download / share / email


class NoteRow(BaseModel):
    """One contract-note row. Carries an opaque, session-scoped ``downloadToken``
    as its download handle — NEVER the FinX ``file_id`` (the contract-note
    endpoints enforce no authentication). The segment badge shows only on
    dual-note days."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    date_label: str
    weekday: str
    download_token: str = Field(alias="downloadToken")
    segment_badge: str | None = None  # e.g. "Equity & F&O" / "Commodity"


class NoteListCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["note_list_card"] = "note_list_card"
    rows: list[NoteRow]
    page_size: int = 10
    total: int = 0
    month_dividers: list[str] = Field(default_factory=list)
    footer_chips: list[Chip] = Field(default_factory=list)  # email-all / change-dates


class DataRow(BaseModel):
    """A ``{label, value}`` row. ``value`` is rendered VERBATIM — the wire type
    does not reshape or numerically parse it (e.g. brokerage ``desc`` is
    pre-formatted rate text)."""

    model_config = ConfigDict(extra="forbid")
    label: str
    value: str


class DataGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    list: list[DataRow]


class DataCard(BaseModel):
    """Dynamic card (brokerage / holding). Iterates whatever the API returns; no
    hardcoded segment names or row counts, no computed rupee figures."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["data_card"] = "data_card"
    groups: list[DataGroup]


class ErrorBubble(BaseModel):
    """Conversational error (never a toast). Copy never exposes Reason strings,
    HTTP codes, or URLs."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["error_bubble"] = "error_bubble"
    code: ErrorCode
    text: str
    chips: list[Chip] = Field(default_factory=list)  # recovery chips


class TicketConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["ticket_confirmation"] = "ticket_confirmation"
    ticket_id: str
    message: str
    # The call-support chip remains available even after a ticket is raised.
    chips: list[Chip] = Field(default_factory=list)


class Generating(BaseModel):
    """Latency indicator emitted when a turn is expected to exceed five seconds."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["generating"] = "generating"
    message: str = "Generating…"


RenderBlock = Annotated[
    Union[
        Bubble,
        UserBubble,
        ChipRow,
        StepperCard,
        Calendar,
        FileCard,
        NoteListCard,
        DataCard,
        ErrorBubble,
        TicketConfirmation,
        Generating,
    ],
    Field(discriminator="type"),
]

#: Adapter for validating / round-tripping a single render block of any type.
RenderBlockAdapter: TypeAdapter[RenderBlock] = TypeAdapter(RenderBlock)

#: The eleven render-block type discriminators.
BLOCK_TYPES: frozenset[str] = frozenset(
    {
        "bubble",
        "user_bubble",
        "chip_row",
        "stepper_card",
        "calendar",
        "file_card",
        "note_list_card",
        "data_card",
        "error_bubble",
        "ticket_confirmation",
        "generating",
    }
)


# ---------------------------------------------------------------------------
# Session-seed config slice (D10)
# ---------------------------------------------------------------------------


class ClientLimits(BaseModel):
    """The client-facing subset of the runtime limits (no server-only knobs)."""

    model_config = ConfigDict(extra="forbid")
    page_size: int
    note_threshold: int
    message_cap: int
    follow_up_cap: int


class WhatsNewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    icon: str
    title: str
    body: str
    cta: Chip | None = None
    min_app_version: str | None = None


class ConfigSlice(BaseModel):
    """The client-relevant config delivered in the first ``/api/chat`` response.

    Carries ONLY entry chips, the greeting, the client-facing limits, and
    ``whats_new``. Server-only config (RAG tunables, per-flow calendar-bound math,
    Freshdesk field mapping) is NEVER included here."""

    model_config = ConfigDict(extra="forbid")
    entry_chips: list[Chip]
    greeting: str
    limits: ClientLimits
    whats_new: list[WhatsNewItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Chat turn request/response envelope (D1: non-streaming, one response per turn)
# ---------------------------------------------------------------------------


class ConversationState(str, Enum):
    greeting = "greeting"
    collecting = "collecting"
    generating = "generating"
    delivered = "delivered"
    error = "error"
    escalated = "escalated"


class Caps(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages_used: int
    messages_cap: int
    follow_ups_used: int


class ChatRequest(BaseModel):
    """One user turn. Carries the SessionContext, the user action (free text OR a
    chip action), the thread_id (absent on the first turn), and the turn_number."""

    model_config = ConfigDict(extra="forbid")
    session: SessionContext
    message: str | None = None  # free text
    action: ChipAction | None = None  # chip action
    thread_id: str | None = None  # absent on the first turn
    turn_number: int = 0


class ChatResponse(BaseModel):
    """One complete turn's response (non-streaming). ``config_slice`` is present
    only on the first (session-seed) response."""

    model_config = ConfigDict(extra="forbid")
    thread_id: str
    turn_number: int
    blocks: list[RenderBlock]
    intent: Intent | None = None
    conversation_state: ConversationState
    caps: Caps
    config_slice: ConfigSlice | None = None


# ---------------------------------------------------------------------------
# Generated JSON Schema of the wire union (D11) + drift support
# ---------------------------------------------------------------------------


class _WireSchemaRoot(BaseModel):
    """Root that references the whole wire contract so a single JSON Schema dump
    captures the request/response envelopes and the render-block union for the
    widget's TypeScript codegen."""

    request: ChatRequest
    response: ChatResponse


def build_wire_schema() -> dict:
    """The canonical JSON Schema of the chat wire contract (by alias)."""
    return _WireSchemaRoot.model_json_schema(by_alias=True)


def wire_schema_json() -> str:
    """Deterministic serialization of the wire schema for the checked-in file."""
    return json.dumps(build_wire_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
