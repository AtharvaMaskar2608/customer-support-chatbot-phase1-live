"""Session bootstrap — the first ``/api/chat`` turn (the session seed).

The frozen ``chat-wire-api`` has a single ``POST /api/chat`` route; the first turn
(``thread_id`` absent) is the bootstrap: a time-aware greeting bubble + the entry
surface's chip row + the client-facing ``config_slice``. Server-clock IST buckets
(morning 06:00–09:00, market 09:15–15:30, post-market 15:30–23:00, else default)
pick the greeting; ``page`` picks the entry surface; every value comes from
``RemoteConfig`` — nothing hardcoded.

``select_greeting`` is re-exported by ``app.main`` (the frozen ``test_main_stub``
imports it from there); this module is its single source of truth.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time

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


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def select_greeting(pool: GreetingPool, client_id: str, now: datetime | None = None) -> str:
    """Pick a time-aware greeting template (server-clock IST buckets) and substitute
    the Client ID. Falls back to the default template outside every window."""
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
    config: RemoteConfig, entry_surface: EntrySurface, client_id: str, now: datetime | None = None
) -> ConfigSlice:
    """Build the client-facing config slice (server-only config excluded — D10)."""
    entry_chips = (
        config.reports_chips if entry_surface is EntrySurface.reports else config.support_chips
    )
    return ConfigSlice(
        entry_chips=entry_chips,
        greeting=select_greeting(config.greeting, client_id, now),
        limits=ClientLimits(
            page_size=config.limits.contract_note_page_size,
            note_threshold=config.limits.note_narrow_threshold,
            message_cap=config.limits.message_cap,
            follow_up_cap=config.limits.follow_up_cap,
        ),
        whats_new=config.whats_new,
    )


def build_session_seed(
    request: ChatRequest,
    config: RemoteConfig,
    thread_id: str | None = None,
    now: datetime | None = None,
) -> ChatResponse:
    """The first-turn (session-seed) response: greeting bubble + entry chips +
    ``config_slice``. Makes NO live FinX/DB calls; ``client_id`` (greeting subject)
    is the session's ``user_id``, never request-body input."""
    session = request.session
    config_slice = build_config_slice(config, session.entry_surface, session.user_id, now)
    return ChatResponse(
        thread_id=thread_id or request.thread_id or str(uuid.uuid4()),
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
