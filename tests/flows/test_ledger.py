"""Spec tests for the Ledger / MTF-Ledger flow (flow-ledger-mtf).

Written FROM THE PROPOSAL (proposal.md + flow spec §"Ledger / MTF Ledger Flow"),
not from the implementation: each test asserts what the change PROMISED — the
GetLedgerDetailsPDF request shape for both report types, the E-* failure mapping,
the 2019 floor / today+7 cap / no-clamp window, the MTF path behind the [CONFIRM]
caveat, the friendly filename, the masked-email branch, and the invariant that the
report URL / registered email never reach a render block.

Fixture-based FinX mocks only (tests/fixtures/finx/*), driven through the REAL
`parse_dotnet_envelope` parser. No live API, no network.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from datetime import date, timedelta

import pytest

from app.contracts.flow import FLOW_ATTR, ByteValidation, FlowSpec, StepKind, StepState
from app.contracts.router import Delivery, Intent
from app.finx.envelopes import Outcome, ParsedEnvelope, parse_dotnet_envelope
from app.finx.models import ENDPOINTS, LedgerPdfRequest
import app.flows.ledger as ledger
from app.flows.ledger import FLOW, LedgerFlow, ReportType

# Fixed "today" so resolved-date copy is deterministic (matches the flow-spec sample).
TODAY = date(2026, 7, 17)
FY_FROM, FY_TO = date(2025, 4, 1), date(2026, 3, 31)

FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "finx"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def _env(name: str, *, http_status: int | None = None) -> ParsedEnvelope:
    """Parse a captured .NET fixture into a ParsedEnvelope via the real parser."""
    return parse_dotnet_envelope(_fixture(name), http_status=http_status)


# ---------------------------------------------------------------------------
# Fakes: a FinXClient facade whose dotnet adapter returns queued envelopes and
# records every request; a scriptable server-side PDF fetch.
# ---------------------------------------------------------------------------

GOOD_PDF = b"%PDF-1.7\n" + b"\x00" * 70_000  # byte-valid, ~60-70 KB


class _FakeDotNet:
    def __init__(self, envelopes: list[ParsedEnvelope] | ParsedEnvelope):
        self._queue = envelopes if isinstance(envelopes, list) else [envelopes]
        self.requests: list[LedgerPdfRequest] = []

    async def get_ledger_details_pdf(self, req: LedgerPdfRequest) -> ParsedEnvelope:
        self.requests.append(req)
        return self._queue[min(len(self.requests) - 1, len(self._queue) - 1)]


class _RaisingDotNet:
    def __init__(self, exc: BaseException):
        self._exc = exc
        self.requests: list[LedgerPdfRequest] = []

    async def get_ledger_details_pdf(self, req: LedgerPdfRequest) -> ParsedEnvelope:
        self.requests.append(req)
        raise self._exc


class _FakeClient:
    def __init__(self, dotnet):
        self.dotnet = dotnet
        # unused-by-ledger facade members (present so it reads like the real facade)
        self.go = self.mis = self.mf = self.coti = None


def _fetch_returning(*payloads: bytes):
    """A fetcher that yields the given payloads in order and records the URLs it saw."""
    seen: list[str] = []
    it = iter(payloads)

    async def fetch(url: str) -> bytes:
        seen.append(url)
        return next(it)

    fetch.seen = seen  # type: ignore[attr-defined]
    return fetch


async def _fetch_raising(url: str) -> bytes:
    raise TimeoutError("boom")


def _run(coro):
    return asyncio.run(coro)


def _serialized(blocks) -> str:
    return "".join(b.model_dump_json() for b in blocks)


# ---------------------------------------------------------------------------
# Discovery / FlowSpec registration
# ---------------------------------------------------------------------------


def test_module_level_flow_is_discoverable_flowspec():
    # The engine's importlib discovery reads the module-level FLOW attribute.
    discovered = getattr(ledger, FLOW_ATTR)
    assert discovered is FLOW
    assert isinstance(discovered, FlowSpec)  # runtime_checkable protocol
    assert isinstance(discovered, LedgerFlow)


def test_flow_intent_and_multi_intent_hint():
    # FlowSpec.intent (the discovery key) is the primary ledger intent.
    assert FLOW.intent is Intent.report_ledger
    # MTF Ledger is the same flow; the additive hint lets discovery key both.
    assert Intent.report_ledger in FLOW.intents
    assert Intent.report_mtf_ledger in FLOW.intents


def test_flow_config_window_floor_cap_no_clamp():
    w = FLOW.config.window
    assert w.floor == date(2019, 1, 1)  # 2019 calendar floor
    assert w.cap_relative_days == 7  # today + 7 [CONFIRM]
    assert w.max_range_years is None  # NO max-range clamp — a 2019->today range is valid
    assert FLOW.config.intent is Intent.report_ledger


def test_flow_steps_sequence():
    ids = [(s.id, s.kind) for s in FLOW.steps()]
    assert ids == [
        ("report_type", StepKind.segment),  # generic chip-row kind (no report_type kind exists)
        ("date_range", StepKind.date_range),
        ("delivery", StepKind.delivery),
        ("generate", StepKind.generate),
    ]


@pytest.mark.parametrize(
    "intent,expected_label",
    [(Intent.report_ledger, "Ledger"), (Intent.report_mtf_ledger, "MTF Ledger")],
)
def test_initial_steps_precompletes_report_type_when_intent_names_it(intent, expected_label):
    steps = ledger.initial_steps(intent)
    assert steps[0].id == "report_type"
    assert steps[0].state is StepState.done  # Step 1 shown pre-completed...
    assert steps[0].selected_label == expected_label
    assert steps[1].state is StepState.active  # ...and Step 2 (date range) opens active


# ---------------------------------------------------------------------------
# Request contract — both report types (doneCondition core)
# ---------------------------------------------------------------------------


def test_ledger_request_download_contract():
    req = ledger.build_ledger_request(
        client_code="X008593",
        session_id="SID-123",
        report_type=ReportType.ledger,
        from_date=FY_FROM,
        to_date=FY_TO,
        delivery=Delivery.in_chat,
    )
    assert req.ClientId == "X008593"
    assert req.LoginId == "X008593"  # client code, NOT the data API's "JIFFY"
    assert req.LoginId != "JIFFY"
    assert req.Group == "GROUP1"  # uppercase on the PDF endpoint
    assert req.Margin == 0  # normal ledger
    assert req.RequestFor == 0  # download
    assert req.FromDate == "2025-04-01" and req.ToDate == "2026-03-31"
    assert req.SessionId == "SID-123"


def test_mtf_request_sets_margin_1_and_email_request_for_1():
    req = ledger.build_ledger_request(
        client_code="X008593",
        session_id="SID-123",
        report_type=ReportType.mtf,
        from_date=FY_FROM,
        to_date=FY_TO,
        delivery=Delivery.email,
    )
    assert req.Margin == 1  # MTF discriminator [CONFIRM — unproven]
    assert req.RequestFor == 1  # email [CONFIRM]
    assert req.Group == "GROUP1"
    assert req.LoginId == "X008593"


def test_margin_map_and_confirm_caveat_is_carried():
    # MTF drives Margin:1; the [CONFIRM] caveat is carried in the frozen endpoint spec.
    assert ledger.MARGIN == {ReportType.ledger: 0, ReportType.mtf: 1}
    confirm = ENDPOINTS["GetLedgerDetailsPDF"].confirm
    assert any("MTF" in c and "unverified" in c for c in confirm)
    assert any("RequestFor:1" in c for c in confirm)


def test_full_walk_drives_request_for_both_types():
    # A full step walk for BOTH Ledger and MTF drives GetLedgerDetailsPDF correctly.
    for rt, margin in ((ReportType.ledger, 0), (ReportType.mtf, 1)):
        dotnet = _FakeDotNet(_env("ledger_pdf_success.json"))
        blocks = _run(
            ledger.generate_and_deliver(
                _FakeClient(dotnet),
                _fetch_returning(GOOD_PDF),
                client_code="X008593",
                session_id="SID",
                report_type=rt,
                from_date=FY_FROM,
                to_date=FY_TO,
                delivery=Delivery.in_chat,
            )
        )
        assert dotnet.requests[0].Margin == margin
        assert dotnet.requests[0].Group == "GROUP1"
        assert dotnet.requests[0].LoginId == "X008593"
        assert blocks[-1].type == "file_card"


# ---------------------------------------------------------------------------
# Date window: 2019 floor, today+7 cap, no clamp
# ---------------------------------------------------------------------------


def test_window_bounds_and_in_window():
    floor, cap = ledger.window_bounds(TODAY)
    assert floor == date(2019, 1, 1)
    assert cap == TODAY + timedelta(days=7)
    assert ledger.in_window(date(2019, 1, 1), TODAY) is True  # floor allowed
    assert ledger.in_window(date(2018, 12, 31), TODAY) is False  # older hard-disabled
    assert ledger.in_window(date(2017, 6, 1), TODAY) is False
    assert ledger.in_window(cap, TODAY) is True  # today+7 allowed
    assert ledger.in_window(cap + timedelta(days=1), TODAY) is False  # beyond cap


def test_range_in_window_no_max_span_clamp():
    # A full 2019 -> today range is valid (EC-6: no clamp exists).
    assert ledger.range_in_window(date(2019, 1, 1), TODAY, TODAY) is True
    # Floor -> cap is valid.
    assert ledger.range_in_window(*ledger.window_bounds(TODAY), TODAY) is True
    # Reversed range invalid; below-floor invalid.
    assert ledger.range_in_window(TODAY, date(2019, 1, 1), TODAY) is False
    assert ledger.range_in_window(date(2018, 1, 1), TODAY, TODAY) is False


def test_calendar_block_bounds():
    cal = ledger.build_calendar(TODAY)
    assert cal.min_date == date(2019, 1, 1)
    assert cal.max_date == TODAY + timedelta(days=7)
    assert cal.max_range_days is None  # no clamp
    assert cal.disabled_ranges == []


# ---------------------------------------------------------------------------
# Presets, out-of-window nudge, future clamp
# ---------------------------------------------------------------------------


def test_date_presets_show_resolved_dates():
    row = ledger.date_preset_chips(TODAY)
    labels = [c.label for c in row.chips]
    assert labels[0] == "Last 3 months"
    # "Last FY" resolves to the last completed FY with dates shown (V2 style).
    assert labels[1] == "Last FY · 1 Apr 2025 – 31 Mar 2026"
    assert "Custom range" in labels[2]
    # The Last FY chip carries the resolved range as its payload.
    fy_chip = row.chips[1]
    assert fy_chip.action.payload == {"from": "2025-04-01", "to": "2026-03-31"}


def test_out_of_window_nudge_makes_no_api_call():
    blocks = ledger.out_of_window_response(TODAY)  # pure — no client, no fetch
    assert blocks[0].type == "bubble"
    assert blocks[0].text == (
        "I can pull ledger entries from Jan 2019 onwards — records before that "
        "aren't available here. Want the earliest possible instead?"
    )
    chips = blocks[1].chips
    assert chips[0].label == "Jan 2019 – Dec 2020"
    assert chips[0].action.payload == {"from": "2019-01-01", "to": "2020-12-31"}
    assert "Pick dates" in chips[1].label


def test_future_clamp_confirm_uses_cap():
    blocks = ledger.future_clamp_confirm(TODAY)
    # today+7 = 24 Jul 2026
    assert blocks[0].text == "I can include up to 24 Jul 2026 — set that as the end date?"


# ---------------------------------------------------------------------------
# Download delivery + byte validation + one silent retry
# ---------------------------------------------------------------------------


def _download(dotnet, fetch, rt=ReportType.ledger, delivery=Delivery.in_chat, **kw):
    return _run(
        ledger.generate_and_deliver(
            _FakeClient(dotnet),
            fetch,
            client_code="X008593",
            session_id="SID",
            report_type=rt,
            from_date=FY_FROM,
            to_date=FY_TO,
            delivery=delivery,
            **kw,
        )
    )


def test_download_success_delivers_renamed_file_card_no_password():
    dotnet = _FakeDotNet(_env("ledger_pdf_success.json"))
    blocks = _download(dotnet, _fetch_returning(GOOD_PDF))
    assert [b.type for b in blocks] == ["bubble", "file_card"]
    assert blocks[0].text == "Here's your Ledger for 1 Apr 2025 – 31 Mar 2026"
    card = blocks[1]
    assert card.filename == "Ledger_1Apr2025-31Mar2026.pdf"  # friendly, no client code
    assert card.format == "pdf"
    assert card.password_hint is None  # ledger PDFs are not password protected
    assert card.size_label.endswith("KB")
    labels = [c.label for c in card.actions]
    assert labels == ["↺ Send it again", "✉️ Email it instead", "\U0001f3ab Raise a ticket"]


def test_mtf_download_uses_mtf_filename_and_caption():
    dotnet = _FakeDotNet(_env("ledger_pdf_success.json"))
    blocks = _download(dotnet, _fetch_returning(GOOD_PDF), rt=ReportType.mtf)
    assert blocks[0].text == "Here's your MTF Ledger for 1 Apr 2025 – 31 Mar 2026"
    assert blocks[1].filename == "MTF_Ledger_1Apr2025-31Mar2026.pdf"


def test_broken_bytes_trigger_exactly_one_silent_retry_then_efetch():
    dotnet = _FakeDotNet(_env("ledger_pdf_success.json"))
    fetch = _fetch_returning(b"<html>404</html>", b"<html>404</html>")
    blocks = _download(dotnet, fetch)
    # exactly one silent retry => two generations, two fetches.
    assert len(dotnet.requests) == ByteValidation().silent_retries + 1 == 2
    assert len(fetch.seen) == 2
    assert blocks[0].type == "error_bubble"
    assert blocks[0].code.value == "E-FETCH"
    assert blocks[0].text == "The ledger generated but didn't come through cleanly on my side."


def test_silent_retry_recovers_when_second_fetch_is_valid():
    dotnet = _FakeDotNet(_env("ledger_pdf_success.json"))
    fetch = _fetch_returning(b"broken", GOOD_PDF)  # first broken, retry good
    blocks = _download(dotnet, fetch)
    assert len(dotnet.requests) == 2
    assert blocks[-1].type == "file_card"


def test_short_pdf_below_min_bytes_is_invalid():
    dotnet = _FakeDotNet(_env("ledger_pdf_success.json"))
    tiny = b"%PDF-1.7 tiny"  # valid magic but under the 1024 size floor
    blocks = _download(dotnet, _fetch_returning(tiny, tiny))
    assert blocks[0].type == "error_bubble" and blocks[0].code.value == "E-FETCH"


def test_report_url_never_appears_in_delivered_blocks():
    dotnet = _FakeDotNet(_env("ledger_pdf_success.json"))
    fetch = _fetch_returning(GOOD_PDF)
    blocks = _download(dotnet, fetch)
    dump = _serialized(blocks)
    # The server-side URL was fetched but is never surfaced.
    assert "choiceindia.com" not in dump
    assert "PDFReports" not in dump
    assert "http" not in dump
    assert fetch.seen[0]  # the fetcher did receive a (server-side) URL


# ---------------------------------------------------------------------------
# Failure mapping: no-data, auth, timeout, unknown
# ---------------------------------------------------------------------------


def test_no_data_ledger_maps_to_e_nodata_with_range_copy():
    dotnet = _FakeDotNet(_env("ledger_no_data.json"))
    blocks = _run(
        ledger.generate_and_deliver(
            _FakeClient(dotnet),
            _fetch_returning(GOOD_PDF),
            client_code="X",
            session_id="S",
            report_type=ReportType.ledger,
            from_date=date(2026, 4, 14),
            to_date=date(2026, 7, 14),
            delivery=Delivery.in_chat,
        )
    )
    assert blocks[0].type == "error_bubble"
    assert blocks[0].code.value == "E-NODATA"
    assert blocks[0].text == (
        "No ledger entries found between 14 Apr and 14 Jul 2026, so there's nothing to report there."
    )
    assert [c.label for c in blocks[0].chips] == ["Try a different range", "\U0001f3ab Raise a ticket"]


def test_no_data_mtf_uses_plain_copy_no_education():
    dotnet = _FakeDotNet(_env("ledger_no_data.json"))
    blocks = _download(dotnet, _fetch_returning(GOOD_PDF), rt=ReportType.mtf)
    assert blocks[0].code.value == "E-NODATA"
    assert blocks[0].text == "No data available for MTF Ledger in that range."
    labels = [c.label for c in blocks[0].chips]
    assert labels == ["Try Ledger instead", "Try a different range"]


def test_auth_error_maps_to_session_expiry_bubble_not_error_code():
    dotnet = _FakeDotNet(_env("dotnet_401.json", http_status=401))
    blocks = _download(dotnet, _fetch_returning(GOOD_PDF))
    assert [b.type for b in blocks] == ["bubble", "chip_row"]
    assert blocks[0].text == "Your session timed out… your selections are saved."
    assert blocks[1].chips[0].label == "Log in again"
    # The raw Reason ("Invalid SessionId") is never surfaced.
    assert "SessionId" not in _serialized(blocks)


def test_generic_error_maps_to_e_unknown():
    dotnet = _FakeDotNet(ParsedEnvelope(outcome=Outcome.error, payload="", reason="boom"))
    blocks = _download(dotnet, _fetch_returning(GOOD_PDF))
    assert blocks[0].type == "error_bubble" and blocks[0].code.value == "E-UNKNOWN"
    assert "boom" not in _serialized(blocks)  # reason not leaked


def test_client_timeout_maps_to_e_timeout():
    dotnet = _RaisingDotNet(TimeoutError())
    blocks = _download(dotnet, _fetch_returning(GOOD_PDF))
    assert blocks[0].type == "error_bubble" and blocks[0].code.value == "E-TIMEOUT"


def test_fetch_timeout_maps_to_e_timeout():
    dotnet = _FakeDotNet(_env("ledger_pdf_success.json"))
    blocks = _download(dotnet, _fetch_raising)
    assert blocks[0].type == "error_bubble" and blocks[0].code.value == "E-TIMEOUT"


# ---------------------------------------------------------------------------
# Email branch (RequestFor:1) — masked address, never the full email
# ---------------------------------------------------------------------------


def test_email_branch_masks_registered_address():
    env = ParsedEnvelope(
        outcome=Outcome.success,
        payload="Ledger Report mail sent successfully to SANJAY.HARSHA@GMAIL.COM",
        reason="",
    )
    dotnet = _FakeDotNet(env)
    blocks = _download(dotnet, _fetch_returning(GOOD_PDF), delivery=Delivery.email)
    assert dotnet.requests[0].RequestFor == 1  # email branch
    assert [b.type for b in blocks] == ["bubble", "bubble", "chip_row"]
    assert blocks[0].text == (
        "Done — your Ledger for 1 Apr 2025 – 31 Mar 2026 is on its way to san***.harsha@gmail.com."
    )
    assert blocks[1].text == "Usually arrives within 2 minutes."
    labels = [c.label for c in blocks[2].chips]
    assert labels == ["↺ Resend", "\U0001f4c4 Get it here as PDF", "\U0001f3ab Raise a ticket"]
    # The full (unmasked) address never appears anywhere.
    assert "sanjay.harsha@gmail.com" not in _serialized(blocks).lower()


def test_mask_email_forms():
    assert ledger.mask_email("SANJAY.HARSHA@GMAIL.COM") == "san***.harsha@gmail.com"
    assert ledger.mask_email("BOB@EXAMPLE.COM") == "bob***@example.com"
    assert ledger.mask_email("not-an-email") == "your registered email"


def test_email_no_data_still_maps_to_nodata():
    dotnet = _FakeDotNet(_env("ledger_no_data.json"))
    blocks = _download(dotnet, _fetch_returning(GOOD_PDF), delivery=Delivery.email)
    assert blocks[0].code.value == "E-NODATA"


# ---------------------------------------------------------------------------
# Filename / caption formatting
# ---------------------------------------------------------------------------


def test_filename_and_caption_formatting():
    assert ledger.display_filename(ReportType.ledger, FY_FROM, FY_TO) == "Ledger_1Apr2025-31Mar2026.pdf"
    assert ledger.display_filename(ReportType.mtf, FY_FROM, FY_TO) == "MTF_Ledger_1Apr2025-31Mar2026.pdf"
    assert ledger.caption(ReportType.ledger, FY_FROM, FY_TO) == "Here's your Ledger for 1 Apr 2025 – 31 Mar 2026"
    assert ledger.caption(ReportType.mtf, FY_FROM, FY_TO) == "Here's your MTF Ledger for 1 Apr 2025 – 31 Mar 2026"
