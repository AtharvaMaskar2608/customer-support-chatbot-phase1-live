"""Fixture-based tests for the single-shot Brokerage flow.

Written FROM the proposal's done condition, not from the implementation:
  * the module is discovered/registered and satisfies the frozen ``FlowSpec``;
  * the intent drives exactly one ``get-brokerage-slab`` call keyed by the
    PascalCase one-word ``ClientID``;
  * the ``Response`` array renders as a data card with segments AND rows iterated
    DYNAMICALLY (a variant fixture with a different segment set / row count proves
    nothing is hardcoded) and ``desc`` rendered VERBATIM (no computed rupee
    figure);
  * there is no PDF / email / file path and no URL or email on the card;
  * an API failure triggers exactly one silent retry, then the conversational
    error bubble.

Offline only: a minimal fake ``go`` adapter returns ``ParsedEnvelope``s produced
by the real hybrid-envelope parser from the frozen fixture / inline captures.
"""

from __future__ import annotations

import json
import pathlib

import pytest

import app.flows.brokerage as brokerage
from app.contracts.errors import ErrorCode
from app.contracts.flow import FLOW_ATTR, FlowSpec
from app.contracts.router import Intent
from app.contracts.wire import (
    Bubble,
    ChipActionKind,
    ChipRow,
    DataCard,
    ErrorBubble,
)
from app.finx.envelopes import ParsedEnvelope, parse_dotnet_envelope
from app.finx.models import BrokerageSlabRequest

CLIENT_ID = "X008593"

_FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "finx"

# The variant capture — a DIFFERENT segment set and different row counts from the
# frozen 4-segment fixture. If anything were hardcoded to Equity/Derivative/…,
# this would not render correctly.
_VARIANT_RESPONSE = [
    {"title": "Mutual Fund", "list": [{"title": "Direct", "desc": "₹0 flat"}]},
    {
        "title": "Bonds",
        "list": [
            {"title": "Primary", "desc": "₹5.00 per unit"},
            {"title": "Secondary", "desc": "₹2.50 per unit"},
            {"title": "Sovereign Gold", "desc": "₹0.00 for the first ₹1 lakh"},
        ],
    },
]


def _load_success_body() -> dict:
    return json.loads((_FIXTURE_DIR / "brokerage_hybrid_success.json").read_text())


def _success_env(response: list) -> ParsedEnvelope:
    return parse_dotnet_envelope(
        {"StatusCode": 200, "Status": "Success", "Response": response, "Reason": ""}
    )


def _frozen_success_env() -> ParsedEnvelope:
    # Exercise the real hybrid-envelope parser on the frozen capture verbatim.
    return parse_dotnet_envelope(_load_success_body())


def _error_env() -> ParsedEnvelope:
    return parse_dotnet_envelope(
        {"StatusCode": 500, "Status": "Fail", "Response": None, "Reason": "upstream boom"}
    )


class _FakeGo:
    """A minimal fake of the JWT ``go`` adapter. Returns the queued
    ``ParsedEnvelope``s (or raises a queued exception) and records every request."""

    def __init__(self, outcomes: list) -> None:
        self._queue = list(outcomes)
        self.requests: list[BrokerageSlabRequest] = []

    async def get_brokerage_slab(self, req: BrokerageSlabRequest) -> ParsedEnvelope:
        self.requests.append(req)
        if not self._queue:
            raise AssertionError("get_brokerage_slab called more times than expected")
        result = self._queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _FakeFinX:
    def __init__(self, *outcomes) -> None:
        self.go = _FakeGo(list(outcomes))


def _block_types(blocks) -> list[str]:
    return [b.type for b in blocks]


def _iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _iter_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _iter_strings(v)


# ---------------------------------------------------------------------------
# Registration / spec conformance
# ---------------------------------------------------------------------------


def test_flow_is_discovered_and_satisfies_frozen_flowspec():
    flow = getattr(brokerage, FLOW_ATTR)
    assert isinstance(flow, FlowSpec)
    assert flow.intent is Intent.report_brokerage
    assert flow.config.intent is Intent.report_brokerage


def test_brokerage_is_single_shot_no_steps_no_window():
    flow = brokerage.FLOW
    assert tuple(flow.steps()) == ()
    window = flow.config.window
    assert window.floor is None
    assert window.cap_relative_days is None
    assert window.max_range_years is None
    assert window.fy_based is False


# ---------------------------------------------------------------------------
# Intent → one call keyed by ClientID → dynamic, verbatim data card
# ---------------------------------------------------------------------------


async def test_intent_drives_exactly_one_call_keyed_by_clientid():
    finx = _FakeFinX(_frozen_success_env())
    blocks = await brokerage.FLOW.handle(CLIENT_ID, finx)

    assert len(finx.go.requests) == 1
    req = finx.go.requests[0]
    assert isinstance(req, BrokerageSlabRequest)
    # The identity-field trap: the request key is PascalCase one-word ``ClientID``.
    assert req.model_dump() == {"ClientID": CLIENT_ID}
    assert _block_types(blocks) == ["data_card"]


async def test_frozen_fixture_renders_all_segments_and_rows_verbatim():
    finx = _FakeFinX(_frozen_success_env())
    (card,) = await brokerage.FLOW.handle(CLIENT_ID, finx)
    assert isinstance(card, DataCard)

    body = _load_success_body()["Response"]
    # Every segment and every row is rendered, in order, dynamically.
    assert [g.title for g in card.groups] == [g["title"] for g in body]
    for group, src in zip(card.groups, body):
        assert [r.label for r in group.list] == [r["title"] for r in src["list"]]
        # ``desc`` is rendered VERBATIM into ``value`` — no reshaping, no computed
        # rupee figure.
        assert [r.value for r in group.list] == [r["desc"] for r in src["list"]]


async def test_variant_fixture_proves_no_hardcoded_segments_or_row_count():
    finx = _FakeFinX(_success_env(_VARIANT_RESPONSE))
    (card,) = await brokerage.FLOW.handle(CLIENT_ID, finx)
    assert isinstance(card, DataCard)

    assert [g.title for g in card.groups] == ["Mutual Fund", "Bonds"]
    # Row counts differ per segment (1 vs 3) — iterated dynamically.
    assert [len(g.list) for g in card.groups] == [1, 3]
    assert card.groups[1].list[2].label == "Sovereign Gold"
    assert card.groups[1].list[2].value == "₹0.00 for the first ₹1 lakh"


async def test_data_card_carries_no_url_or_email():
    finx = _FakeFinX(_frozen_success_env())
    (card,) = await brokerage.FLOW.handle(CLIENT_ID, finx)

    # ``_iter_strings`` yields every dict key AND every string value in the card.
    strings = set(_iter_strings(card.model_dump()))
    forbidden_keys = {"url", "report_url", "file_id", "cmlLink", "cml_link", "email", "server_filename"}
    assert not (forbidden_keys & strings)
    for s in strings:
        assert "http" not in s.lower()
        assert "@" not in s
        assert "mailto" not in s.lower()


# ---------------------------------------------------------------------------
# One silent retry, then the conversational error bubble
# ---------------------------------------------------------------------------


async def test_api_failure_retries_once_silently_then_error_bubble():
    finx = _FakeFinX(_error_env(), _error_env())
    blocks = await brokerage.FLOW.handle(CLIENT_ID, finx)

    # Exactly one silent retry: two calls total, no third.
    assert len(finx.go.requests) == 2
    assert _block_types(blocks) == ["error_bubble"]
    (bubble,) = blocks
    assert isinstance(bubble, ErrorBubble)
    assert bubble.code is ErrorCode.E_TIMEOUT
    assert bubble.text == brokerage.FETCH_ERROR_TEXT
    # Recovery chips live on the bubble (never a toast).
    kinds = [c.action.kind for c in bubble.chips]
    assert kinds == [ChipActionKind.retry, ChipActionKind.raise_ticket]
    # The server Reason / HTTP code / URL never appear in user copy.
    assert "boom" not in bubble.text
    assert "500" not in bubble.text


async def test_transient_failure_recovers_on_the_silent_retry():
    finx = _FakeFinX(TimeoutError("network"), _frozen_success_env())
    blocks = await brokerage.FLOW.handle(CLIENT_ID, finx)

    assert len(finx.go.requests) == 2
    assert _block_types(blocks) == ["data_card"]


async def test_empty_response_array_is_treated_as_a_fetch_failure():
    finx = _FakeFinX(_success_env([]), _success_env([]))
    blocks = await brokerage.FLOW.handle(CLIENT_ID, finx)

    assert len(finx.go.requests) == 2
    assert _block_types(blocks) == ["error_bubble"]


async def test_transport_exception_on_both_calls_yields_error_bubble():
    finx = _FakeFinX(TimeoutError("t1"), ConnectionError("t2"))
    blocks = await brokerage.FLOW.handle(CLIENT_ID, finx)

    assert len(finx.go.requests) == 2
    assert _block_types(blocks) == ["error_bubble"]


# ---------------------------------------------------------------------------
# No PDF / email / file path anywhere
# ---------------------------------------------------------------------------


async def test_no_path_ever_produces_a_file_or_email_block():
    groups = brokerage._parse_groups(_load_success_body()["Response"])
    responses = [
        await brokerage.FLOW.handle(CLIENT_ID, _FakeFinX(_frozen_success_env())),
        brokerage.no_document_response(groups),
        brokerage.off_plan_response(groups),
        brokerage.calculation_pointer_response(groups),
        brokerage.fetch_error_response(),
    ]
    for blocks in responses:
        for t in _block_types(blocks):
            assert t not in {"file_card", "note_list_card", "calendar", "stepper_card"}


def test_module_constructs_no_file_card():
    # A static guard on the "no PDF/email path exists" done-condition clause.
    src = pathlib.Path(brokerage.__file__).read_text()
    assert "FileCard" not in src
    assert "file_card" not in src


# ---------------------------------------------------------------------------
# Card-only edge cases (EC-4 / EC-5-6 / EC-7)
# ---------------------------------------------------------------------------


def test_ec7_no_document_ask_explains_and_reshows_card():
    groups = brokerage._parse_groups(_load_success_body()["Response"])
    blocks = brokerage.no_document_response(groups)
    assert _block_types(blocks) == ["bubble", "data_card"]
    assert isinstance(blocks[0], Bubble)
    assert blocks[0].text == brokerage.NO_DOCUMENT_TEXT


def test_ec4_off_plan_shows_plan_plus_ticket_chip():
    groups = brokerage._parse_groups(_load_success_body()["Response"])
    blocks = brokerage.off_plan_response(groups)
    assert _block_types(blocks) == ["bubble", "data_card", "chip_row"]
    chip_row = blocks[2]
    assert isinstance(chip_row, ChipRow)
    assert [c.action.kind for c in chip_row.chips] == [ChipActionKind.raise_ticket]


def test_ec56_calculation_ask_points_to_contract_note_never_computes():
    groups = brokerage._parse_groups(_load_success_body()["Response"])
    blocks = brokerage.calculation_pointer_response(groups)
    assert _block_types(blocks) == ["bubble", "data_card", "chip_row"]
    # The rate rows are re-shown verbatim; no rupee figure is computed.
    card = blocks[1]
    assert card.groups[0].list[0].value == "₹0.10 for trade value of 10 thousand"
    kinds = [c.action.kind for c in blocks[2].chips]
    assert kinds == [ChipActionKind.send_text, ChipActionKind.raise_ticket]
