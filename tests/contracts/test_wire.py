"""chat-wire-api spec tests.

Asserts: SessionContext hides secrets + derives entry_surface; the chat
request/response envelope shape; the 11-type render-block union round-trips and
carries only display-safe fields (no URL/file_id/cmlLink/email keys on
file/note/data cards; note rows carry downloadToken); and the session-seed
config_slice excludes server-only config.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.contracts.errors import ErrorCode
from app.contracts.router import Intent
from app.contracts.wire import (
    BLOCK_TYPES,
    Bubble,
    Calendar,
    Caps,
    ChatRequest,
    ChatResponse,
    Chip,
    ChipAction,
    ChipActionKind,
    ChipRow,
    ClientLimits,
    ConfigSlice,
    ConversationState,
    DataCard,
    DataGroup,
    DataRow,
    EntrySurface,
    ErrorBubble,
    FileCard,
    Generating,
    NoteListCard,
    NoteRow,
    RenderBlockAdapter,
    SessionContext,
    StepperCard,
    StepperStep,
    StepState,
    TicketConfirmation,
    UserBubble,
    WhatsNewItem,
)

FORBIDDEN_KEYS = {"url", "report_url", "file_id", "cmlLink", "cml_link", "email", "server_filename"}


def _all_keys(obj) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _all_keys(item)
    return keys


def test_session_context_hides_secrets():
    ctx = SessionContext.from_url_params(
        userId="X008593",
        sessionId="SECRET_SESSION",
        accessToken="SECRET_JWT",
        isDarkTheme="true",
        platform="web",
        page="support",
    )
    assert ctx.user_id == "X008593"
    assert ctx.session_id == "SECRET_SESSION"  # retained in-process
    assert ctx.access_token == "SECRET_JWT"
    assert ctx.is_dark_theme is True
    # Never serialized.
    dumped = ctx.model_dump()
    assert "session_id" not in dumped and "access_token" not in dumped
    assert "SECRET_SESSION" not in ctx.model_dump_json()
    assert "SECRET_JWT" not in ctx.model_dump_json()


def test_entry_surface_derived_from_page():
    reports = SessionContext.from_url_params(
        userId="X1", sessionId="s", accessToken="a", platform="web", page="reports"
    )
    assert reports.entry_surface is EntrySurface.reports
    support = SessionContext.from_url_params(
        userId="X1", sessionId="s", accessToken="a", platform="web", page="help"
    )
    assert support.entry_surface is EntrySurface.support


def test_chat_envelope():
    ctx = SessionContext.from_url_params(
        userId="X1", sessionId="s", accessToken="a", platform="web", page="support"
    )
    # First turn: no thread_id.
    req = ChatRequest(session=ctx, message="get my p&l")
    assert req.thread_id is None
    assert req.turn_number == 0

    resp = ChatResponse(
        thread_id="t-123",
        turn_number=1,
        blocks=[Bubble(text="Hi")],
        intent=Intent.report_pnl,
        conversation_state=ConversationState.collecting,
        caps=Caps(messages_used=1, messages_cap=10, follow_ups_used=0),
    )
    dumped = resp.model_dump(by_alias=True)
    assert dumped["thread_id"] == "t-123"
    assert dumped["turn_number"] == 1
    assert isinstance(dumped["blocks"], list)
    assert dumped["intent"] == "report_pnl"
    assert dumped["conversation_state"] == "collecting"
    assert dumped["caps"] == {"messages_used": 1, "messages_cap": 10, "follow_ups_used": 0}
    # intent is nullable.
    resp2 = ChatResponse(
        thread_id="t",
        turn_number=1,
        blocks=[Bubble(text="hi")],
        conversation_state=ConversationState.greeting,
        caps=Caps(messages_used=0, messages_cap=10, follow_ups_used=0),
    )
    assert resp2.intent is None


def _sample_blocks() -> list:
    chip = Chip(label="📊 P&L", action=ChipAction(kind=ChipActionKind.send_text, payload={"text": "p&l"}))
    return [
        Bubble(text="Factual answers only.", compliance_footer=True),
        UserBubble(text="get my p&l"),
        ChipRow(chips=[chip]),
        StepperCard(steps=[StepperStep(id="segment", title="Segment", state=StepState.active, chips=[chip])]),
        Calendar(min_date=date(2018, 1, 1), max_date=date(2026, 7, 24), max_range_days=730),
        FileCard(filename="Client_Master_List.pdf", size_label="9 KB", format="pdf", password_hint="PAN", actions=[chip]),
        NoteListCard(
            rows=[NoteRow(date_label="16 Sep 2024", weekday="Mon", download_token="opaque-token-xyz", segment_badge="Equity & F&O")],
            page_size=10,
            total=21,
        ),
        DataCard(groups=[DataGroup(title="Equity", list=[DataRow(label="Intraday", value="₹0.10 for trade value of 10 thousand")])]),
        ErrorBubble(code=ErrorCode.E_FETCH, text="incomplete", chips=[chip]),
        TicketConfirmation(ticket_id="FD-42", message="Raised", chips=[chip]),
        Generating(),
    ]


def test_render_blocks():
    blocks = _sample_blocks()
    # Every one of the 11 block types is represented.
    assert {b.type for b in blocks} == BLOCK_TYPES
    assert len(BLOCK_TYPES) == 11

    for block in blocks:
        payload = block.model_dump(by_alias=True)
        # discriminated on `type`.
        assert payload["type"] in BLOCK_TYPES
        # round-trips through the discriminated union.
        rebuilt = RenderBlockAdapter.validate_python(payload)
        assert rebuilt == block

    # No sensitive identifiers on file / note / data cards.
    for block in blocks:
        if block.type in {"file_card", "note_list_card", "data_card"}:
            keys = _all_keys(block.model_dump(by_alias=True))
            assert keys.isdisjoint(FORBIDDEN_KEYS), (block.type, keys & FORBIDDEN_KEYS)

    # Note-list rows carry downloadToken (camelCase alias), never file_id.
    note_card = next(b for b in blocks if b.type == "note_list_card")
    row_dump = note_card.model_dump(by_alias=True)["rows"][0]
    assert "downloadToken" in row_dump
    assert row_dump["downloadToken"] == "opaque-token-xyz"
    assert "file_id" not in row_dump and "download_token" not in row_dump

    # CML file card uses the server's own filename.
    file_card = next(b for b in blocks if b.type == "file_card")
    assert file_card.filename == "Client_Master_List.pdf"

    # Data-card value is verbatim (no reshaping / rupee computation).
    data_card = next(b for b in blocks if b.type == "data_card")
    assert data_card.groups[0].list[0].value == "₹0.10 for trade value of 10 thousand"


def test_config_slice():
    slice_ = ConfigSlice(
        entry_chips=[Chip(label="📊 Get my P&L", action=ChipAction(kind=ChipActionKind.send_text))],
        greeting="Hey X008593 — what do you need?",
        limits=ClientLimits(page_size=10, note_threshold=50, message_cap=10, follow_up_cap=2),
        whats_new=[WhatsNewItem(icon="⚡", title="11 reports, instant", body="…")],
    )
    keys = _all_keys(slice_.model_dump(by_alias=True))
    # Server-only config is not present anywhere in the slice.
    for forbidden in ("rag_candidate_k", "rrf_k", "rag_context_k", "reranker", "freshdesk", "calendar_bounds"):
        assert forbidden not in keys
    # The client-facing limits ARE present.
    assert "page_size" in keys and "message_cap" in keys


def test_extra_fields_forbidden_on_blocks():
    with pytest.raises(ValidationError):
        Bubble(text="hi", bogus=1)
