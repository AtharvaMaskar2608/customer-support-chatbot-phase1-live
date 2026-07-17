"""FastAPI app — POST /api/chat + session bootstrap (STUB, design D12).

This change writes the stub: the first (session-seed) `/api/chat` response returns
a schema-valid greeting turn (greeting bubble + starter chips + the client-facing
config_slice) using the wire contract, making NO live FinX/DB calls.

After this change, `app/main.py` has exactly ONE owner — the
conversation-orchestrator change — and no other change may edit it. The
store-writer and tracing changes contribute via startup hooks that main.py calls;
they SHALL NOT edit main.py themselves.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config.defaults import DEFAULT_CONFIG
from app.config.schema import GreetingPool, RemoteConfig
from app.contracts.wire import (
    Bubble,
    Caps,
    ChatRequest,
    ChatResponse,
    ChipRow,
    ClientLimits,
    ConfigSlice,
    ConversationState,
    EntrySurface,
)

app = FastAPI(title="Choice Jini", version="0.1.0")


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def select_greeting(pool: GreetingPool, client_id: str, now: datetime | None = None) -> str:
    """Pick a time-aware greeting template and substitute the Client ID."""
    current = (now or datetime.now()).time()
    for template, (start, end) in (
        (pool.morning, pool.morning_range),
        (pool.market_hours, pool.market_hours_range),
        (pool.post_market, pool.post_market_range),
    ):
        if _parse_hhmm(start) <= current < _parse_hhmm(end):
            return template.replace("{client_id}", client_id)
    return pool.default.replace("{client_id}", client_id)


def build_config_slice(
    config: RemoteConfig, entry_surface: EntrySurface, client_id: str
) -> ConfigSlice:
    """Build the client-facing config slice (server-only config excluded)."""
    entry_chips = (
        config.reports_chips if entry_surface is EntrySurface.reports else config.support_chips
    )
    return ConfigSlice(
        entry_chips=entry_chips,
        greeting=select_greeting(config.greeting, client_id),
        limits=ClientLimits(
            page_size=config.limits.contract_note_page_size,
            note_threshold=config.limits.note_narrow_threshold,
            message_cap=config.limits.message_cap,
            follow_up_cap=config.limits.follow_up_cap,
        ),
        whats_new=config.whats_new,
    )


def build_session_seed(request: ChatRequest) -> ChatResponse:
    """The first-turn (session-seed) response: greeting + starter chips + config_slice."""
    session = request.session
    config = DEFAULT_CONFIG
    config_slice = build_config_slice(config, session.entry_surface, session.user_id)
    return ChatResponse(
        thread_id=request.thread_id or str(uuid.uuid4()),
        turn_number=request.turn_number,
        blocks=[
            Bubble(text=config_slice.greeting, compliance_footer=True),
            ChipRow(chips=config_slice.entry_chips),
        ],
        intent=None,
        conversation_state=ConversationState.greeting,
        caps=Caps(
            messages_used=0,
            messages_cap=config.limits.message_cap,
            follow_ups_used=0,
        ),
        config_slice=config_slice,
    )


@app.post("/api/chat")
def chat(request: ChatRequest) -> JSONResponse:
    """Phase-1 non-streaming chat turn. This stub only serves the session seed;
    the conversation-orchestrator change owns the real turn logic."""
    response = build_session_seed(request)
    # Serialize by alias (note-list downloadToken) and mode=json (enums/datetimes).
    return JSONResponse(content=response.model_dump(by_alias=True, mode="json"))
