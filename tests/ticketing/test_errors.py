"""In-band error handling — every Freshdesk non-2xx → ErrorBubble, no raw leak.

Proposal (H8 blocker): no raw error, stack trace, HTTP code, Reason, or URL
reaches the user. Non-2xx maps to E-FETCH (retryable: 429/5xx/transport) or
E-UNKNOWN (4xx). 429 honors Retry-After. Every bubble keeps a call-support chip.
K7: the confirmation never promises a guaranteed time.
"""

from __future__ import annotations

import httpx
import respx

from app.contracts.errors import ErrorCode
from app.contracts.wire import ChipActionKind, ErrorBubble, TicketConfirmation
from app.contracts.router import Intent
from app.ticketing.payload import TranscriptTurn
from app.ticketing.tool import get_ticket_status, raise_ticket

from .conftest import ROOT

TRANSCRIPT = [TranscriptTurn(role="user", content="raise a ticket please")]

#: Fragments that would betray internals if they ever reached the user.
LEAK_FRAGMENTS = [
    "Validation failed",
    "rate limit",
    "exceeded the limit",
    "logged in to perform",
    "http",
    "freshdesk",
    "400",
    "401",
    "429",
    "500",
    "Traceback",
    "unique_external_id",
]


def _assert_no_leak(bubble: ErrorBubble):
    low = bubble.text.lower()
    for frag in LEAK_FRAGMENTS:
        assert frag.lower() not in low, f"leaked {frag!r} in {bubble.text!r}"


def _has_call_support(bubble: ErrorBubble) -> bool:
    return any(c.action.kind == ChipActionKind.call_support for c in bubble.chips)


def _has_retry(bubble: ErrorBubble) -> bool:
    return any(c.action.kind == ChipActionKind.retry for c in bubble.chips)


async def _raise(session, config, client):
    return await raise_ticket(session, Intent.report_pnl, TRANSCRIPT, config=config, client=client)


@respx.mock
async def test_400_create_maps_to_unknown_no_leak(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_empty.json"))
    )
    respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(400, json=fd_fixture("error_400_missing_field.json"))
    )
    result = await _raise(session, config, client)
    assert isinstance(result, ErrorBubble)
    assert result.code == ErrorCode.E_UNKNOWN
    _assert_no_leak(result)
    assert _has_call_support(result)


@respx.mock
async def test_401_create_maps_to_unknown(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_empty.json"))
    )
    respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(401, json=fd_fixture("error_401.json"))
    )
    result = await _raise(session, config, client)
    assert isinstance(result, ErrorBubble)
    assert result.code == ErrorCode.E_UNKNOWN
    _assert_no_leak(result)


@respx.mock
async def test_429_maps_to_fetch_retryable_honoring_retry_after(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(
            429, headers={"Retry-After": "30"}, json=fd_fixture("error_429.json")
        )
    )
    result = await _raise(session, config, client)
    assert isinstance(result, ErrorBubble)
    assert result.code == ErrorCode.E_FETCH  # retryable
    assert _has_retry(result)
    assert _has_call_support(result)
    _assert_no_leak(result)


@respx.mock
async def test_500_maps_to_fetch_retryable(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_empty.json"))
    )
    respx.post(f"{ROOT}/tickets").mock(return_value=httpx.Response(500, text="<html>Server Error</html>"))
    result = await _raise(session, config, client)
    assert isinstance(result, ErrorBubble)
    assert result.code == ErrorCode.E_FETCH
    _assert_no_leak(result)


@respx.mock
async def test_transport_failure_maps_to_fetch(session, config, client):
    respx.get(f"{ROOT}/tickets").mock(side_effect=httpx.ConnectError("connection refused"))
    result = await _raise(session, config, client)
    assert isinstance(result, ErrorBubble)
    assert result.code == ErrorCode.E_FETCH
    _assert_no_leak(result)


@respx.mock
async def test_status_by_id_404_is_friendly_not_found(session, config, client):
    respx.get(f"{ROOT}/tickets/999999").mock(return_value=httpx.Response(404, json={"description": "not found"}))
    result = await get_ticket_status(session, ticket_id=999999, config=config, client=client)
    assert isinstance(result, ErrorBubble)
    assert result.code == ErrorCode.E_UNKNOWN
    assert "couldn't find" in result.text.lower()
    _assert_no_leak(result)


@respx.mock
async def test_status_transport_failure_maps_to_fetch(session, config, client):
    respx.get(f"{ROOT}/tickets").mock(side_effect=httpx.ReadTimeout("timeout"))
    result = await get_ticket_status(session, ticket_id=None, config=config, client=client)
    assert isinstance(result, ErrorBubble)
    assert result.code == ErrorCode.E_FETCH
    _assert_no_leak(result)


@respx.mock
async def test_confirmation_promises_no_guaranteed_time(session, config, client, fd_fixture):
    respx.get(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(200, json=fd_fixture("list_empty.json"))
    )
    respx.post(f"{ROOT}/tickets").mock(
        return_value=httpx.Response(201, json=fd_fixture("create_201.json"))
    )
    result = await _raise(session, config, client)
    assert isinstance(result, TicketConfirmation)
    low = result.message.lower()
    assert "24" not in low
    assert "hour" not in low
    assert "minute" not in low
    # call-support chip stays visible on the confirmation
    assert any(c.action.kind == ChipActionKind.call_support for c in result.chips)


async def test_missing_api_key_is_unknown_not_crash(session):
    """A deployment misconfig (no key) surfaces as E-UNKNOWN, never a crash/leak."""
    from app.ticketing.config import load_config

    broken = load_config(env={})  # no FRESHDESK_API_KEY
    result = await raise_ticket(session, Intent.report_pnl, TRANSCRIPT, config=broken)
    assert isinstance(result, ErrorBubble)
    assert result.code == ErrorCode.E_UNKNOWN
