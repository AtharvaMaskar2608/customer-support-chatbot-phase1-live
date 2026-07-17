"""Server-side ticketing tool functions (frozen tool names ``raise_ticket`` /
``get_ticket_status``).

These are the functions the orchestrator binds to the frozen native-tool
definitions. Identity is server-side: the requester ClientID is always
``session.user_id`` — a model-supplied client id is never forwarded (spec §2.6).

``raise_ticket`` flow: session-scoped idempotency guard → real-time open-ticket
check (short-circuit to a private note + surface the existing ticket) → create →
``TicketConfirmation``. ``get_ticket_status``: by id (view+stats) or by ClientID
(most-recent-first) → ``DataCard``. Every Freshdesk non-2xx becomes an
``ErrorBubble`` (E-FETCH retryable / E-UNKNOWN) with no raw leak (H8); the raw
status/code is logged server-side only, never a ticket id or URL.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

import httpx

from app.contracts.errors import ErrorCode
from app.contracts.router import Intent
from app.contracts.wire import (
    Chip,
    ChipAction,
    ChipActionKind,
    DataCard,
    DataGroup,
    DataRow,
    ErrorBubble,
    SessionContext,
    TicketConfirmation,
)
from app.ticketing.client import FreshdeskAPIError, FreshdeskClient, FreshdeskConfigError
from app.ticketing.config import FreshdeskConfig, default_config
from app.ticketing.mapping import freshdesk_type_for_intent, status_copy
from app.ticketing.payload import (
    ConversationTranscript,
    build_description,
    build_ticket_payload,
)

logger = logging.getLogger("app.ticketing")

#: Freshdesk statuses that count as "open" for dedupe (2 Open, 3 Pending).
OPEN_STATUSES: frozenset[int] = frozenset({2, 3})

_RAISE = "raise"
_STATUS = "status"

# --- user-facing copy (ticketing-specific; the frozen ERROR_COPY is report-flow
# copy). Never contains a Reason string, HTTP code, or URL (H8). ------------
_NEW_TICKET_MSG = "Ticket #{id} raised — our team will get back to you as per our support policy."
_EXISTING_TICKET_MSG = (
    "You already have an open ticket (#{id}) for this — I've added your latest "
    "details to it. Our team will respond as per our support policy."
)
_FETCH_COPY = {
    _RAISE: "I couldn't reach our ticketing system just now — want me to try again?",
    _STATUS: "I couldn't reach our ticketing system to check that just now — try again in a moment?",
}
_UNKNOWN_COPY = {
    _RAISE: "Something went wrong raising your ticket. You can still reach our team on call support.",
    _STATUS: "Something went wrong checking your ticket. You can still reach our team on call support.",
}
_NOT_FOUND_COPY = "I couldn't find a ticket with that number."

#: Session-scoped idempotency guard: hash(ClientID+query_type+conversation_id) →
#: ticket_id. Prevents a double-create within one conversation. A durable
#: cross-session table is deferred (no migration ownership) — this resets on
#: process restart, which is acceptable for the within-turn double-create it guards.
_IDEMPOTENCY_CACHE: dict[str, str] = {}


def reset_idempotency_cache() -> None:
    """Clear the in-memory idempotency guard (used by tests)."""
    _IDEMPOTENCY_CACHE.clear()


def _idem_key(client_id: str, query_type: Intent, conversation_id: str) -> str:
    qt = query_type.value if isinstance(query_type, Intent) else str(query_type)
    raw = f"{client_id}|{qt}|{conversation_id}".encode()
    return hashlib.sha256(raw).hexdigest()


# --- chips -----------------------------------------------------------------


def _call_support_chip() -> Chip:
    return Chip(label="📞 Call support", action=ChipAction(kind=ChipActionKind.call_support))


def _retry_chip() -> Chip:
    return Chip(label="↺ Retry", action=ChipAction(kind=ChipActionKind.retry))


# --- confirmations ---------------------------------------------------------


def _new_confirmation(ticket_id: str) -> TicketConfirmation:
    return TicketConfirmation(
        ticket_id=ticket_id,
        message=_NEW_TICKET_MSG.format(id=ticket_id),
        chips=[_call_support_chip()],  # call-support stays visible (proposal)
    )


def _existing_confirmation(ticket_id: str) -> TicketConfirmation:
    return TicketConfirmation(
        ticket_id=ticket_id,
        message=_EXISTING_TICKET_MSG.format(id=ticket_id),
        chips=[_call_support_chip()],
    )


# --- error bubbles ---------------------------------------------------------


def _fetch_error_bubble(context: str) -> ErrorBubble:
    return ErrorBubble(
        code=ErrorCode.E_FETCH,
        text=_FETCH_COPY[context],
        chips=[_retry_chip(), _call_support_chip()],
    )


def _unknown_error_bubble(context: str) -> ErrorBubble:
    return ErrorBubble(
        code=ErrorCode.E_UNKNOWN,
        text=_UNKNOWN_COPY[context],
        chips=[_call_support_chip()],
    )


def _not_found_bubble() -> ErrorBubble:
    return ErrorBubble(
        code=ErrorCode.E_UNKNOWN,
        text=_NOT_FOUND_COPY,
        chips=[_call_support_chip()],
    )


def _api_error_bubble(err: FreshdeskAPIError, context: str) -> ErrorBubble:
    # Server-side only; deliberately excludes any ticket id / URL.
    logger.warning(
        "freshdesk api error context=%s status=%s code=%s field=%s retry_after=%s",
        context,
        err.status_code,
        err.code,
        err.field,
        err.retry_after,
    )
    # 429 (honor Retry-After, logged above) and 5xx are transient → retryable.
    if err.status_code == 429 or err.status_code >= 500:
        return _fetch_error_bubble(context)
    return _unknown_error_bubble(context)


# --- open-ticket dedupe ----------------------------------------------------


def _first_open_same_type(
    tickets: list[dict], query_type: Intent, config: FreshdeskConfig
) -> dict | None:
    """The first open (status 2/3) ticket for this requester of the same query
    type. When Types are off, any open ticket for the requester matches (all Jini
    tickets then share the pinned cascade and are indistinguishable)."""
    mapped_type = freshdesk_type_for_intent(query_type, config)
    for ticket in tickets:
        if ticket.get("status") not in OPEN_STATUSES:
            continue
        if mapped_type is None or ticket.get("type") == mapped_type:
            return ticket
    return None


async def _resolve_duplicate(
    client: FreshdeskClient,
    *,
    session: SessionContext,
    query_type: Intent,
    transcript: ConversationTranscript,
    language: str,
    config: FreshdeskConfig,
    now: datetime | None,
) -> str | None:
    """Best-effort recovery for a 409 create: find the open ticket, append the
    context as a private note, and surface it. Secondary failures are swallowed —
    surfacing the existing ticket still succeeds."""
    try:
        tickets = await client.list_by_external_id(session.user_id)
    except (FreshdeskAPIError, httpx.HTTPError):
        return None
    existing = _first_open_same_type(tickets, query_type, config)
    if existing is None:
        return None
    try:
        note = build_description(
            session=session,
            query_type=query_type,
            transcript=transcript,
            language=language,
            config=config,
            raised_at=now or datetime.now(),
        )
        await client.add_note(existing["id"], note, private=True)
    except (FreshdeskAPIError, httpx.HTTPError):
        pass
    return str(existing["id"])


# --- public tool functions -------------------------------------------------


async def raise_ticket(
    session: SessionContext,
    query_type: Intent,
    transcript: ConversationTranscript,
    language: str = "en",
    conversation_id: str | None = None,
    *,
    config: FreshdeskConfig | None = None,
    client: FreshdeskClient | None = None,
    now: datetime | None = None,
) -> TicketConfirmation | ErrorBubble:
    """Raise (or dedupe to) a Freshdesk ticket carrying the transcript."""
    config = config or default_config()
    try:
        client = client or FreshdeskClient.from_config(config)
    except FreshdeskConfigError:
        logger.error("ticketing misconfigured: no Freshdesk API key/root resolvable")
        return _unknown_error_bubble(_RAISE)

    client_id = session.user_id
    key = _idem_key(client_id, query_type, conversation_id) if conversation_id else None
    if key is not None and key in _IDEMPOTENCY_CACHE:
        # Already created within this conversation — surface it, do not re-create.
        return _existing_confirmation(_IDEMPOTENCY_CACHE[key])

    try:
        tickets = await client.list_by_external_id(client_id)
        existing = _first_open_same_type(tickets, query_type, config)
        if existing is not None:
            note = build_description(
                session=session,
                query_type=query_type,
                transcript=transcript,
                language=language,
                config=config,
                raised_at=now or datetime.now(),
            )
            await client.add_note(existing["id"], note, private=True)
            ticket_id = str(existing["id"])
            if key is not None:
                _IDEMPOTENCY_CACHE[key] = ticket_id
            return _existing_confirmation(ticket_id)

        payload = build_ticket_payload(
            session=session,
            query_type=query_type,
            transcript=transcript,
            language=language,
            config=config,
            now=now,
        )
        created = await client.create_ticket(payload)
        ticket_id = str(created["id"])
        if key is not None:
            _IDEMPOTENCY_CACHE[key] = ticket_id
        return _new_confirmation(ticket_id)

    except FreshdeskAPIError as err:
        if err.status_code == 409:
            duplicate = await _resolve_duplicate(
                client,
                session=session,
                query_type=query_type,
                transcript=transcript,
                language=language,
                config=config,
                now=now,
            )
            if duplicate is not None:
                if key is not None:
                    _IDEMPOTENCY_CACHE[key] = duplicate
                return _existing_confirmation(duplicate)
        return _api_error_bubble(err, _RAISE)
    except httpx.HTTPError:
        logger.warning("freshdesk transport failure context=%s", _RAISE)
        return _fetch_error_bubble(_RAISE)


async def get_ticket_status(
    session: SessionContext,
    ticket_id: int | None = None,
    *,
    config: FreshdeskConfig | None = None,
    client: FreshdeskClient | None = None,
) -> DataCard | ErrorBubble:
    """Look up ticket status by explicit id, else the requester's tickets
    (most-recent-first). Renders a ``DataCard``, never raw JSON."""
    config = config or default_config()
    try:
        client = client or FreshdeskClient.from_config(config)
    except FreshdeskConfigError:
        logger.error("ticketing misconfigured: no Freshdesk API key/root resolvable")
        return _unknown_error_bubble(_STATUS)

    try:
        if ticket_id is not None:
            ticket = await client.get_ticket(ticket_id, include="stats")
            return _single_status_card(ticket)
        tickets = await client.list_by_external_id(session.user_id)
        if not tickets:
            return _no_tickets_card()
        return _list_status_card(tickets)
    except FreshdeskAPIError as err:
        if ticket_id is not None and err.status_code == 404:
            return _not_found_bubble()
        return _api_error_bubble(err, _STATUS)
    except httpx.HTTPError:
        logger.warning("freshdesk transport failure context=%s", _STATUS)
        return _fetch_error_bubble(_STATUS)


# --- status cards ----------------------------------------------------------


def _single_status_card(ticket: dict) -> DataCard:
    rows = [DataRow(label="Status", value=status_copy(ticket.get("status")))]
    subject = ticket.get("subject")
    if subject:
        rows.append(DataRow(label="Subject", value=str(subject)))
    updated = ticket.get("updated_at")
    if updated:
        rows.append(DataRow(label="Last updated", value=str(updated)))
    return DataCard(groups=[DataGroup(title=f"Ticket #{ticket.get('id')}", list=rows)])


def _list_status_card(tickets: list[dict]) -> DataCard:
    rows = [
        DataRow(label=f"Ticket #{ticket.get('id')}", value=status_copy(ticket.get("status")))
        for ticket in tickets[:10]  # most-recent-first; cap the card
    ]
    return DataCard(groups=[DataGroup(title="Your tickets", list=rows)])


def _no_tickets_card() -> DataCard:
    return DataCard(
        groups=[
            DataGroup(
                title="Your tickets",
                list=[DataRow(label="No tickets", value="You don't have any support tickets yet.")],
            )
        ]
    )


#: Tool-registration surface: the orchestrator binds these by their frozen tool
#: names (matches ``app.contracts.tools.TOOL_NAMES``).
TICKETING_TOOLS = {
    "raise_ticket": raise_ticket,
    "get_ticket_status": get_ticket_status,
}
