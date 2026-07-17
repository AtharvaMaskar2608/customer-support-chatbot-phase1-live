"""Fixture-based tests for the CML flow (flow-cml).

Written from the proposal's done-condition, not from the implementation: each test
asserts what the spec promised. No live API, no engine, no network — the FinX MIS
adapter and the server-side byte fetcher are injected fakes, and the success / 401
envelopes come from the 2026-07-16 capture fixtures under ``tests/fixtures/finx/``.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.contracts.errors import ERROR_COPY, ErrorCode
from app.contracts.flow import FlowSpec
from app.contracts.router import Intent
from app.contracts.wire import ChipActionKind, SessionContext
from app.finx.envelopes import ParsedEnvelope, parse_mis_envelope
from app.finx.models import CmlRequest
from app.flows import cml

FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "finx"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


# A valid PDF payload above the frozen 1 KB size floor, and invalid variants.
PDF_BYTES = b"%PDF-1.6\n" + b"0" * 4096
NOT_PDF_BYTES = b"<html><body>404 Not Found</body></html>" + b" " * 4096
TOO_SMALL_PDF = b"%PDF-1.6"  # correct magic, below the min_bytes floor

SUCCESS_ENV = parse_mis_envelope(_fixture("cml_success.json"), http_status=200)
AUTH_401_ENV = parse_mis_envelope(_fixture("cml_401.json"), http_status=401)
UNKNOWN_ENV = parse_mis_envelope(
    {"statusCode": 500, "message": "boom", "devMessage": None, "body": {}},
    http_status=200,
)
EMPTY_BODY_ENV = parse_mis_envelope(
    {"statusCode": 200, "message": "URL generated successfully", "devMessage": None, "body": {}},
    http_status=200,
)

CML_LINK = _fixture("cml_success.json")["body"]["cmlLink"]


class FakeMis:
    """Records every request and replays a queue of ParsedEnvelope | Exception,
    repeating the last entry once the queue is exhausted."""

    def __init__(self, results: list[ParsedEnvelope | Exception]) -> None:
        self._results = list(results)
        self.calls: list[CmlRequest] = []

    async def generate_report(self, req: CmlRequest) -> ParsedEnvelope:
        self.calls.append(req)
        item = self._results[min(len(self.calls) - 1, len(self._results) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    """Facade exposing only the ``mis`` adapter (the only one CML uses)."""

    def __init__(self, mis: FakeMis) -> None:
        self.mis = mis
        self.dotnet = self.go = self.mf = self.coti = None


class FakeFetcher:
    """Server-side byte fetcher fake. Records the URLs it was handed and replays a
    queue of bytes | Exception, repeating the last entry when exhausted."""

    def __init__(self, results: list[bytes | Exception]) -> None:
        self._results = list(results)
        self.urls: list[str] = []

    async def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        item = self._results[min(len(self.urls) - 1, len(self._results) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def _ctx() -> SessionContext:
    return SessionContext.from_url_params(
        userId="X008593",
        sessionId="SID-should-never-be-used",
        accessToken="JWT-sso-access-token",
        isDarkTheme=False,
        platform="android",
        page="reports",
    )


def _blocks_json(blocks) -> str:
    return "".join(b.model_dump_json(by_alias=True) for b in blocks)


# ---------------------------------------------------------------------------
# Discovery / registration
# ---------------------------------------------------------------------------


def test_flow_is_discoverable_flowspec():
    assert isinstance(cml.FLOW, FlowSpec)
    assert cml.FLOW.intent is Intent.report_cml
    # The module exposes FLOW under the frozen discovery attribute name.
    from app.contracts.flow import FLOW_ATTR

    assert getattr(cml, FLOW_ATTR) is cml.FLOW


def test_flow_is_zero_step_generate():
    steps = list(cml.FLOW.steps())
    # No user-input collection steps — a single terminal generate step.
    assert len(steps) == 1
    assert steps[0].kind.value == "generate"
    # No calendar / date window (CML takes no input).
    win = cml.FLOW.config.window
    assert win.floor is None and win.cap_relative_days is None and not win.fy_based


# ---------------------------------------------------------------------------
# Request shape + JWT (SessionId is never used)
# ---------------------------------------------------------------------------


async def test_request_shape_and_no_sessionid():
    mis = FakeMis([SUCCESS_ENV])
    fetcher = FakeFetcher([PDF_BYTES])
    ctx = _ctx()

    await cml.run(FakeClient(mis), ctx, fetcher)

    assert len(mis.calls) == 1
    req = mis.calls[0]
    assert req == CmlRequest(reportType="cml", searchBy="client-id", searchValue="X008593")
    # searchValue is the session Client ID, never the SessionId.
    assert req.searchValue == ctx.user_id
    assert req.searchValue != ctx.session_id
    # The request model structurally cannot carry a SessionId.
    dumped = req.model_dump()
    assert "SessionId" not in dumped and "sessionId" not in dumped
    assert ctx.session_id not in json.dumps(dumped)


# ---------------------------------------------------------------------------
# Success delivery
# ---------------------------------------------------------------------------


async def test_success_delivers_cml_file_card():
    mis = FakeMis([SUCCESS_ENV])
    fetcher = FakeFetcher([PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)

    # File card + post-delivery chip row.
    assert [b.type for b in blocks] == ["file_card", "chip_row"]
    card = blocks[0]
    # §2.6 carve-out: keep the server's own filename.
    assert card.filename == "Client_Master_List.pdf"
    assert card.format == "pdf"
    # [ASSUMPTION] unprotected — no password line.
    assert card.password_hint is None
    assert card.helper == "Trouble opening it? Tell me."
    assert card.size_label  # non-empty human size
    # The link was fetched server-side.
    assert fetcher.urls == [CML_LINK]


async def test_post_delivery_chips():
    mis = FakeMis([SUCCESS_ENV])
    fetcher = FakeFetcher([PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    chip_row = blocks[1]
    labels = [c.label for c in chip_row.chips]
    assert labels == ["↺ Send it again", "Something incorrect in it? 🎫 Raise a ticket"]
    kinds = [c.action.kind for c in chip_row.chips]
    assert kinds == [ChipActionKind.retry, ChipActionKind.raise_ticket]
    # "Send it again" signals a cache-bypassing regeneration.
    assert chip_row.chips[0].action.payload == {"resend": "true"}


# ---------------------------------------------------------------------------
# FLAG B — the signed link is never surfaced
# ---------------------------------------------------------------------------


async def test_link_never_surfaced_in_any_block():
    mis = FakeMis([SUCCESS_ENV])
    fetcher = FakeFetcher([PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    serialized = _blocks_json(blocks)
    assert CML_LINK not in serialized
    assert "onmedia.choiceindia.com" not in serialized
    assert "X-Amz-Signature" not in serialized
    assert "http" not in serialized.lower()


# ---------------------------------------------------------------------------
# "Send it again" re-calls the API (never reuses the dead link)
# ---------------------------------------------------------------------------


async def test_resend_recalls_the_api():
    mis = FakeMis([SUCCESS_ENV])
    fetcher = FakeFetcher([PDF_BYTES])
    client = FakeClient(mis)
    ctx = _ctx()

    await cml.run(client, ctx, fetcher)
    await cml.run(client, ctx, fetcher, resend=True)

    # Two independent generations — a fresh API call each time.
    assert len(mis.calls) == 2
    # A fresh server-side fetch each time (the prior signed link is dead).
    assert len(fetcher.urls) == 2


# ---------------------------------------------------------------------------
# Error mapping (emit codes; copy comes from the frozen taxonomy)
# ---------------------------------------------------------------------------


async def test_auth_401_maps_to_e_unknown():
    mis = FakeMis([AUTH_401_ENV])
    fetcher = FakeFetcher([PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    assert [b.type for b in blocks] == ["error_bubble"]
    assert blocks[0].code is ErrorCode.E_UNKNOWN
    # No byte fetch is attempted on an auth failure.
    assert fetcher.urls == []
    # Copy is the frozen taxonomy's, verbatim — not redefined by the flow.
    assert blocks[0].text == ERROR_COPY[ErrorCode.E_UNKNOWN].text


async def test_unknown_non_200_maps_to_e_unknown():
    mis = FakeMis([UNKNOWN_ENV])
    fetcher = FakeFetcher([PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    assert blocks[0].type == "error_bubble"
    assert blocks[0].code is ErrorCode.E_UNKNOWN
    assert fetcher.urls == []


async def test_missing_cmllink_maps_to_e_unknown():
    mis = FakeMis([EMPTY_BODY_ENV])
    fetcher = FakeFetcher([PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    assert blocks[0].type == "error_bubble"
    assert blocks[0].code is ErrorCode.E_UNKNOWN
    assert fetcher.urls == []


async def test_timeout_on_fetch_maps_to_e_timeout():
    mis = FakeMis([SUCCESS_ENV])
    fetcher = FakeFetcher([TimeoutError("byte fetch timed out")])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    assert blocks[0].type == "error_bubble"
    assert blocks[0].code is ErrorCode.E_TIMEOUT
    assert blocks[0].text == ERROR_COPY[ErrorCode.E_TIMEOUT].text


async def test_timeout_on_api_maps_to_e_timeout():
    mis = FakeMis([TimeoutError("api timed out")])
    fetcher = FakeFetcher([PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    assert blocks[0].code is ErrorCode.E_TIMEOUT
    assert fetcher.urls == []


# ---------------------------------------------------------------------------
# Byte validation + exactly one silent retry then E-FETCH
# ---------------------------------------------------------------------------


async def test_wrong_magic_one_silent_retry_then_e_fetch():
    mis = FakeMis([SUCCESS_ENV, SUCCESS_ENV])
    fetcher = FakeFetcher([NOT_PDF_BYTES, NOT_PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    assert blocks[0].type == "error_bubble"
    assert blocks[0].code is ErrorCode.E_FETCH
    # Exactly one silent retry, each retry a FRESH API call (the old link is dead).
    assert len(mis.calls) == 2
    assert len(fetcher.urls) == 2


async def test_silent_retry_recovers_and_delivers():
    mis = FakeMis([SUCCESS_ENV, SUCCESS_ENV])
    fetcher = FakeFetcher([NOT_PDF_BYTES, PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    assert [b.type for b in blocks] == ["file_card", "chip_row"]
    assert blocks[0].filename == "Client_Master_List.pdf"
    assert len(mis.calls) == 2
    assert len(fetcher.urls) == 2


async def test_below_size_floor_is_invalid():
    mis = FakeMis([SUCCESS_ENV])
    fetcher = FakeFetcher([TOO_SMALL_PDF, TOO_SMALL_PDF])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    # Correct magic but below the 1 KB floor → fetch failure after one retry.
    assert blocks[0].type == "error_bubble"
    assert blocks[0].code is ErrorCode.E_FETCH


async def test_recovery_chips_come_from_frozen_taxonomy():
    mis = FakeMis([AUTH_401_ENV])
    fetcher = FakeFetcher([PDF_BYTES])

    blocks = await cml.run(FakeClient(mis), _ctx(), fetcher)
    chip_labels = tuple(c.label for c in blocks[0].chips)
    # Verbatim from ERROR_COPY — the flow does not invent error chip copy.
    assert chip_labels == ERROR_COPY[ErrorCode.E_UNKNOWN].chips
