"""Ticket-status lookup (proposal §"Ticket-status lookup").

By explicit id (view+stats) or by ClientID (most-recent-first). Status enum →
user copy (2 Open / 3 Pending / 4 Resolved / 5 Closed). Renders a DataCard,
never raw JSON.
"""

from __future__ import annotations

import httpx
import respx

from app.contracts.wire import DataCard
from app.ticketing.tool import get_ticket_status

from .conftest import ROOT


def _all_row_text(card: DataCard) -> str:
    return " ".join(
        f"{row.label} {row.value}" for group in card.groups for row in group.list
    )


@respx.mock
async def test_status_by_id_renders_data_card_with_status_copy(session, config, client, fd_fixture):
    route = respx.get(f"{ROOT}/tickets/7529083").mock(
        return_value=httpx.Response(200, json=fd_fixture("view_stats.json"))
    )
    result = await get_ticket_status(session, ticket_id=7529083, config=config, client=client)
    assert isinstance(result, DataCard)
    text = _all_row_text(result)
    assert "Pending" in text  # status 3 → Pending
    assert "3" not in [
        row.value for group in result.groups for row in group.list
    ]  # never the raw enum int as a value
    # includes ?include=stats
    assert route.calls.last.request.url.params["include"] == "stats"


@respx.mock
async def test_status_by_client_lists_most_recent_first(session, config, client, fd_fixture):
    route = respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_multi.json"))
    )
    result = await get_ticket_status(session, ticket_id=None, config=config, client=client)
    assert isinstance(result, DataCard)
    rows = [row for group in result.groups for row in group.list]
    # first row is the most-recently-updated ticket (7529090, Pending)
    assert rows[0].label == "Ticket #7529090"
    assert rows[0].value == "Pending"
    assert rows[1].value == "Resolved"  # status 4
    assert route.calls.last.request.url.params["unique_external_id"] == "X008593"


@respx.mock
async def test_status_by_client_when_none_returns_empty_card(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_empty.json"))
    )
    result = await get_ticket_status(session, ticket_id=None, config=config, client=client)
    assert isinstance(result, DataCard)  # a friendly empty-state card, not a crash
    assert "don't have any" in _all_row_text(result).lower()


@respx.mock
async def test_all_four_statuses_map_to_copy(session, config, client):
    for status_int, copy in [(2, "Open"), (3, "Pending"), (4, "Resolved"), (5, "Closed")]:
        respx.get(f"{ROOT}/tickets/999").mock(
            return_value=httpx.Response(200, json={"id": 999, "status": status_int})
        )
        result = await get_ticket_status(session, ticket_id=999, config=config, client=client)
        assert copy in _all_row_text(result)
        respx.reset()
