"""Duplicate prevention / open-ticket awareness (proposal §"Duplicate prevention").

Proposal: before creating, check the REAL-TIME list-by-requester endpoint; if an
open ticket on the same query type exists, append a private note and surface it
instead of creating. The search endpoint is secondary only. A session-scoped
idempotency guard prevents a double-create within one conversation.
"""

from __future__ import annotations

import httpx
import respx

from app.contracts.router import Intent
from app.contracts.wire import TicketConfirmation
from app.ticketing.payload import TranscriptTurn
from app.ticketing.tool import raise_ticket

from .conftest import ROOT

TRANSCRIPT = [TranscriptTurn(role="user", content="where is my P&L?")]


async def _raise(session, config, client, **kw):
    return await raise_ticket(
        session,
        kw.pop("intent", Intent.report_pnl),
        TRANSCRIPT,
        config=config,
        client=client,
        **kw,
    )


@respx.mock
async def test_creates_when_no_open_ticket(session, config, client, fd_fixture):
    list_route = respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_empty.json"))
    )
    create_route = respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(201, json=fd_fixture("create_201.json"))
    )
    result = await _raise(session, config, client)
    assert isinstance(result, TicketConfirmation)
    assert result.ticket_id == "7529084"
    assert list_route.called
    assert create_route.called
    # the create body is the built payload
    sent = create_route.calls.last.request
    import json as _json

    body = _json.loads(sent.content)
    assert body["unique_external_id"] == "X008593"
    assert body["group_id"] == 22000168676


@respx.mock
async def test_uses_realtime_list_endpoint_ordered_desc(session, config, client, fd_fixture):
    list_route = respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_empty.json"))
    )
    respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(201, json=fd_fixture("create_201.json"))
    )
    await _raise(session, config, client)
    url = list_route.calls.last.request.url
    assert url.params["unique_external_id"] == "X008593"
    assert url.params["order_by"] == "updated_at"
    assert url.params["order_type"] == "desc"


@respx.mock
async def test_open_same_type_appends_note_and_does_not_create(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_open_reports.json"))
    )
    note_route = respx.post(f"{ROOT}/tickets/7529083/notes").mock(
        return_value=httpx.Response(201, json=fd_fixture("note_201.json"))
    )
    create_route = respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(201, json=fd_fixture("create_201.json"))
    )
    result = await _raise(session, config, client)
    assert isinstance(result, TicketConfirmation)
    assert result.ticket_id == "7529083"  # surfaces the EXISTING ticket
    assert note_route.called
    assert not create_route.called
    # the note is private
    import json as _json

    note_body = _json.loads(note_route.calls.last.request.content)
    assert note_body["private"] is True


@respx.mock
async def test_closed_ticket_does_not_block_create(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_closed_only.json"))
    )
    create_route = respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(201, json=fd_fixture("create_201.json"))
    )
    result = await _raise(session, config, client)
    assert isinstance(result, TicketConfirmation)
    assert create_route.called  # a resolved/closed ticket is not a duplicate


@respx.mock
async def test_open_ticket_of_different_type_does_not_block(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_other_type_open.json"))
    )
    create_route = respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(201, json=fd_fixture("create_201.json"))
    )
    # request is report_pnl (→ REPORTS); the open ticket is CONTRACT NOTES
    result = await _raise(session, config, client, intent=Intent.report_pnl)
    assert isinstance(result, TicketConfirmation)
    assert create_route.called


@respx.mock
async def test_session_idempotency_guard_prevents_double_create(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_empty.json"))
    )
    create_route = respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(201, json=fd_fixture("create_201.json"))
    )
    first = await _raise(session, config, client, conversation_id="conv-1")
    second = await _raise(session, config, client, conversation_id="conv-1")
    assert first.ticket_id == second.ticket_id == "7529084"
    assert create_route.call_count == 1  # second call short-circuits


@respx.mock
async def test_409_at_create_falls_back_to_existing(session, config, client, fd_fixture):
    # First list (pre-create dedupe) is empty → we attempt create → 409 →
    # re-list finds the racing open ticket → note + surface.
    respx.get(f"{ROOT}/tickets").mock(
        side_effect=[
            httpx.Response(200, json=fd_fixture("list_empty.json")),
            httpx.Response(200, json=fd_fixture("list_open_reports.json")),
        ]
    )
    respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(409, json=fd_fixture("error_409_duplicate.json"))
    )
    note_route = respx.post(f"{ROOT}/tickets/7529083/notes").mock(
        return_value=httpx.Response(201, json=fd_fixture("note_201.json"))
    )
    result = await _raise(session, config, client)
    assert isinstance(result, TicketConfirmation)
    assert result.ticket_id == "7529083"
    assert note_route.called


@respx.mock
async def test_search_endpoint_is_available_as_secondary(client, fd_fixture):
    """The search endpoint (secondary/reporting only) is implemented and quotes
    its query per 04 §4."""
    search_route = respx.get(f"{ROOT}/search/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("search_open.json"))
    )
    data = await client.search_tickets("cf_client_id:'X008593' AND (status:2 OR status:3)")
    assert data["total"] == 1
    query = search_route.calls.last.request.url.params["query"]
    assert query.startswith('"') and query.endswith('"')  # double-quoted
