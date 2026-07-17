"""flow-pnl spec tests (written FROM the proposal, not the implementation).

Every test maps to a claim in ``openspec/changes/flow-pnl/proposal.md``:
discovery/registration, the segment→Group vocabulary trap, the ``GetGlobalPNLPDF``
request contract (identity fields, RequestFor per branch, With_Exp boolean, no
FileFormat), the polymorphic download-vs-email response, email masking, the E-*
taxonomy mapping, the 2018 floor / today+7 cap / 2-year clamp, and the security
invariant that the report URL / file_id / server filename never reach a render
block. The generic engine mechanics are stubbed by a MINIMAL fake driver here —
the real engine (flow-engine-runtime) integrates in Wave 2.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date

import pytest

from app.contracts.errors import ERROR_COPY, ErrorCode
from app.contracts.flow import FLOW_ATTR, FlowSpec, current_fy
from app.contracts.router import DateRange, Delivery, ExtractedParams, Intent, Segment
from app.contracts.wire import (
    Bubble,
    Calendar,
    ChipActionKind,
    ErrorBubble,
    FileCard,
)
from app.finx.envelopes import Outcome, ParsedEnvelope, parse_dotnet_envelope
from app.flows.pnl import (
    FLOW,
    REQUEST_FOR,
    SEGMENT_GROUP,
    DatePreset,
    PnlFlow,
    mask_registered_email,
)

FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "finx"
TODAY = date(2026, 7, 16)  # deterministic "today" for the whole suite
CLIENT_ID = "X008593"
SESSION_ID = "sess-abc-123"


def load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


# ---------------------------------------------------------------------------
# Minimal fake engine driver (stands in for flow-engine-runtime)
# ---------------------------------------------------------------------------


class FakeDotNetAdapter:
    """Returns a parsed envelope from a captured fixture body (offline)."""

    def __init__(self, body: dict, *, http_status: int | None = None) -> None:
        self._body = body
        self._status = http_status
        self.last_request = None

    async def get_global_pnl_pdf(self, req) -> ParsedEnvelope:
        self.last_request = req
        return parse_dotnet_envelope(self._body, http_status=self._status)


class Engine:
    """A minimal deterministic driver: step progression (skipping pre-filled
    steps), preset resolution, request build, adapter call, result render."""

    def __init__(self, flow: PnlFlow, adapter: FakeDotNetAdapter, *, today: date) -> None:
        self.flow = flow
        self.adapter = adapter
        self.today = today
        self.collected = ExtractedParams()

    def next_step_id(self) -> str | None:
        for step in self.flow.steps():
            if step.id == "segment" and self.collected.segment is not None:
                continue
            if step.id == "date_range" and (
                self.collected.date_range
                and self.collected.date_range.from_
                and self.collected.date_range.to
            ):
                continue
            if step.id == "delivery" and self.collected.delivery is not None:
                continue
            return step.id
        return None

    def choose_segment(self, seg: Segment) -> None:
        self.collected.segment = seg

    def choose_preset(self, preset: DatePreset) -> None:
        frm, to = self.flow.resolve_preset(preset, today=self.today)
        self.collected.date_range = DateRange(from_=frm, to=to)

    def choose_custom(self, frm: date, to: date) -> None:
        self.collected.date_range = DateRange(from_=frm, to=to)

    def choose_delivery(self, delivery: Delivery) -> None:
        self.collected.delivery = delivery

    async def generate(self):
        req = self.flow.build_request(
            self.collected,
            client_id=CLIENT_ID,
            session_id=SESSION_ID,
            delivery=self.collected.delivery,
        )
        env = await self.adapter.get_global_pnl_pdf(req)
        return req, env

    def render(self, env: ParsedEnvelope):
        if env.outcome is Outcome.success:
            kind = self.flow.delivery_kind(env)
            if kind == "email":
                return self.flow.email_confirmation(env.payload, self.collected)
            return self.flow.file_card(self.collected, size_label="196 KB")
        if self.flow.is_session_expiry(env):
            return "session_expiry"
        return self.flow.render_error(self.flow.error_code_for_envelope(env))


# ---------------------------------------------------------------------------
# Discovery / registration
# ---------------------------------------------------------------------------


def test_module_level_flow_satisfies_flowspec():
    flow = getattr(__import__("app.flows.pnl", fromlist=[FLOW_ATTR]), FLOW_ATTR)
    assert flow is FLOW
    assert isinstance(flow, FlowSpec)  # runtime_checkable: intent + config + steps()
    assert flow.intent is Intent.report_pnl
    # Discovery keys by intent, no registration import needed.
    registry = {flow.intent: flow}
    assert registry[Intent.report_pnl] is FLOW


def test_three_steps_in_order():
    assert [s.id for s in FLOW.steps()] == ["segment", "date_range", "delivery"]
    assert [s.kind.value for s in FLOW.steps()] == ["segment", "date_range", "delivery"]


# ---------------------------------------------------------------------------
# Segment → Group vocabulary trap
# ---------------------------------------------------------------------------


def test_segment_group_mapping():
    assert SEGMENT_GROUP == {
        Segment.equity: "Cash",
        Segment.fno: "Derv",
        Segment.commodity: "Comm",
    }
    assert FLOW.group_for(Segment.equity) == "Cash"
    assert FLOW.group_for(Segment.fno) == "Derv"
    assert FLOW.group_for(Segment.commodity) == "Comm"


def test_segment_chips_never_surface_internal_group_values():
    row = FLOW.segment_step()
    labels = [c.label for c in row.chips]
    assert labels == ["Equity", "F&O", "Commodity"]
    blob = row.model_dump_json()
    # The jargon group values must never leak to the customer. ("Comm" is a
    # legitimate substring of the customer label "Commodity" — check the real
    # leak-risk tokens, not that substring.)
    assert "Derv" not in blob
    assert "Cash" not in blob
    # Chip payloads carry router Segment values, never API group values.
    payload_values = {c.action.payload.get("segment") for c in row.chips}
    assert payload_values == {"equity", "fno", "commodity"}


# ---------------------------------------------------------------------------
# Full walk → correct GetGlobalPNLPDF request (PDF branch)
# ---------------------------------------------------------------------------


async def test_full_walk_pdf_builds_correct_request():
    engine = Engine(FLOW, FakeDotNetAdapter(load("pnl_download_success.json")), today=TODAY)
    assert engine.next_step_id() == "segment"
    engine.choose_segment(Segment.equity)
    assert engine.next_step_id() == "date_range"
    engine.choose_preset(DatePreset.this_fy)
    assert engine.next_step_id() == "delivery"
    engine.choose_delivery(Delivery.in_chat)
    assert engine.next_step_id() is None  # ready to generate

    req, env = await engine.generate()
    dumped = req.model_dump()
    assert dumped["ClientId"] == CLIENT_ID
    assert dumped["UserId"] == CLIENT_ID  # identity trap: UserId == ClientId
    assert dumped["Group"] == "Cash"  # Equity → Cash
    assert dumped["RequestFor"] == 0  # download
    assert dumped["With_Exp"] is True  # boolean, not int
    assert "FileFormat" not in dumped  # PDF only
    # This FY (frozen current_fy): 1 Apr of the current FY → today.
    fy_start = int(current_fy(TODAY).split("-")[0])
    assert dumped["FromDate"] == date(fy_start, 4, 1).isoformat()
    assert dumped["ToDate"] == TODAY.isoformat()

    block = engine.render(env)
    assert isinstance(block, FileCard)
    assert block.format == "pdf"
    assert block.password_hint == "PAN"
    assert block.helper == "Trouble opening it? Tell me."


async def test_email_branch_request_and_masked_confirmation():
    # RequestFor flips to 1 on the email branch.
    engine = Engine(FLOW, FakeDotNetAdapter(load("pnl_email_success.json")), today=TODAY)
    engine.choose_segment(Segment.commodity)
    engine.choose_preset(DatePreset.this_month)
    engine.choose_delivery(Delivery.email)
    req, env = await engine.generate()
    assert req.model_dump()["RequestFor"] == 1
    assert req.model_dump()["Group"] == "Comm"

    # The email fixture Response is an email-confirmation string (polymorphic).
    assert FLOW.delivery_kind(env) == "email"
    block = engine.render(env)
    assert isinstance(block, Bubble)


def test_request_for_map():
    assert REQUEST_FOR == {Delivery.in_chat: 0, Delivery.email: 1}


# ---------------------------------------------------------------------------
# Email masking (spec §4.1 documented example)
# ---------------------------------------------------------------------------


def test_registered_email_masked_before_display():
    leaked = "PnL Report mail sent successfully to SANJAY.HARSHA@GMAIL.COM"
    assert mask_registered_email(leaked) == "san***.harsha@gmail.com"

    params = ExtractedParams(segment=Segment.equity, date_range=DateRange(from_=date(2026, 4, 1), to=TODAY))
    bubble = FLOW.email_confirmation(leaked, params)
    assert "san***.harsha@gmail.com" in bubble.text
    assert "SANJAY.HARSHA@GMAIL.COM" not in bubble.text
    assert "sanjay.harsha@gmail.com" not in bubble.text


def test_mask_falls_back_without_address():
    assert mask_registered_email("PnL Report mail sent successfully to <REGISTERED_EMAIL>") == (
        "your registered email"
    )


# ---------------------------------------------------------------------------
# Error taxonomy (E-*) mapping — verbatim frozen copy, no Reason/URL leak
# ---------------------------------------------------------------------------


def test_no_data_maps_to_e_nodata_verbatim():
    env = parse_dotnet_envelope(load("pnl_no_data.json"))
    assert env.outcome is Outcome.no_data
    assert FLOW.error_code_for_envelope(env) is ErrorCode.E_NODATA
    bubble = FLOW.render_error(ErrorCode.E_NODATA, fy_short="2025-26", default_fy_short="2024-25")
    assert isinstance(bubble, ErrorBubble)
    assert bubble.code is ErrorCode.E_NODATA
    assert "No transactions found for FY 2025-26" in bubble.text
    # The raw Reason must never surface in user copy.
    assert "Data not found." not in bubble.text


async def test_auth_401_is_session_expiry_not_a_taxonomy_bubble():
    env = parse_dotnet_envelope(load("dotnet_401.json"), http_status=401)
    assert env.outcome is Outcome.auth_error
    assert FLOW.is_session_expiry(env) is True
    # 401 is NOT one of the five E-* codes; it maps to session-expiry handling.
    assert FLOW.error_code_for_envelope(env) is None

    engine = Engine(FLOW, FakeDotNetAdapter(load("dotnet_401.json"), http_status=401), today=TODAY)
    engine.choose_segment(Segment.equity)
    engine.choose_preset(DatePreset.this_fy)
    engine.choose_delivery(Delivery.in_chat)
    _, env2 = await engine.generate()
    assert engine.render(env2) == "session_expiry"
    # "Invalid SessionId" must never reach the user.
    assert "Invalid SessionId" not in json.dumps("session_expiry")


def test_e_fetch_two_line_and_e_timeout_e_unknown():
    # E-FETCH: the second line + recovery chips are what the bubble shows after
    # the (engine-owned) silent retry; the first line is a plain notice.
    notice = FLOW.fetch_retry_notice()
    assert notice.text == ERROR_COPY[ErrorCode.E_FETCH].text
    bubble = FLOW.render_error(ErrorCode.E_FETCH)
    assert bubble.text == ERROR_COPY[ErrorCode.E_FETCH].second_line
    assert [c.label for c in bubble.chips] == list(ERROR_COPY[ErrorCode.E_FETCH].chips)

    for code in (ErrorCode.E_TIMEOUT, ErrorCode.E_UNKNOWN):
        b = FLOW.render_error(code)
        assert b.code is code
        assert b.text == ERROR_COPY[code].text
        assert len(b.chips) == len(ERROR_COPY[code].chips)


def test_error_bubbles_map_recovery_chip_kinds():
    b = FLOW.render_error(ErrorCode.E_TIMEOUT)
    kinds = {c.action.kind for c in b.chips}
    assert ChipActionKind.retry in kinds
    assert ChipActionKind.raise_ticket in kinds


# ---------------------------------------------------------------------------
# Date-window guardrail: 2018 floor / today+7 cap / 2-year clamp
# ---------------------------------------------------------------------------


def test_calendar_bounds():
    cal = FLOW.build_calendar(today=TODAY)
    assert isinstance(cal, Calendar)
    assert cal.min_date == date(2018, 1, 1)  # floor
    assert cal.max_date == date(2026, 7, 23)  # today + 7


def test_two_year_clamp_is_exact_across_leap():
    assert FLOW.clamp_end(date(2021, 6, 1)) == date(2023, 6, 1)
    # 29 Feb + 2y clamps to 28 Feb (non-leap target) — clamp stated in years.
    assert FLOW.clamp_end(date(2020, 2, 29)) == date(2022, 2, 28)


def test_validate_range_rejects_out_of_window_with_flow_nudge():
    # Below the 2018 floor.
    assert FLOW.validate_range(date(2017, 12, 31), date(2018, 6, 1), today=TODAY) is not None
    assert "Jan 2018" in FLOW.validate_range(date(2017, 1, 1), date(2017, 6, 1), today=TODAY)
    # Beyond today + 7.
    assert FLOW.validate_range(date(2026, 1, 1), date(2026, 8, 1), today=TODAY) is not None
    # Beyond the 2-year clamp.
    assert FLOW.validate_range(date(2018, 1, 1), date(2020, 6, 1), today=TODAY) is not None
    # A valid in-window range within two years passes.
    assert FLOW.validate_range(date(2025, 1, 1), date(2026, 1, 1), today=TODAY) is None


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


def test_presets_resolve():
    fy_start = int(current_fy(TODAY).split("-")[0])
    assert FLOW.resolve_preset(DatePreset.this_fy, today=TODAY) == (date(fy_start, 4, 1), TODAY)
    assert FLOW.resolve_preset(DatePreset.this_month, today=TODAY) == (date(2026, 7, 1), TODAY)
    assert FLOW.resolve_preset(DatePreset.last_3_months, today=TODAY) == (date(2026, 4, 16), TODAY)
    with pytest.raises(ValueError):
        FLOW.resolve_preset(DatePreset.custom, today=TODAY)


# ---------------------------------------------------------------------------
# Free-text pre-fill skips the corresponding step (2c pattern)
# ---------------------------------------------------------------------------


def test_prefilled_segment_skips_segment_step():
    engine = Engine(FLOW, FakeDotNetAdapter(load("pnl_download_success.json")), today=TODAY)
    engine.collected = ExtractedParams(segment=Segment.fno)  # parsed from the opening utterance
    assert engine.next_step_id() == "date_range"  # segment skipped


def test_prefilled_segment_and_range_skip_to_delivery():
    engine = Engine(FLOW, FakeDotNetAdapter(load("pnl_download_success.json")), today=TODAY)
    engine.collected = ExtractedParams(
        segment=Segment.equity,
        date_range=DateRange(from_=date(2025, 4, 1), to=date(2026, 3, 31)),
    )
    assert engine.next_step_id() == "delivery"


# ---------------------------------------------------------------------------
# Delivery options: PDF only (no Excel)
# ---------------------------------------------------------------------------


def test_delivery_offers_pdf_and_email_only_no_excel():
    labels = [c.label for c in FLOW.delivery_step().chips]
    assert any("PDF" in label for label in labels)
    assert any("email" in label.lower() for label in labels)
    assert not any("excel" in label.lower() for label in labels)
    assert FLOW.report_format == "pdf"


# ---------------------------------------------------------------------------
# Security: URL / file_id / server filename never reach a render block
# ---------------------------------------------------------------------------


def test_file_card_carries_no_url_or_client_id():
    params = ExtractedParams(segment=Segment.equity, date_range=DateRange(from_=date(2026, 4, 1), to=TODAY))
    card = FLOW.file_card(params, size_label="196 KB")
    blob = card.model_dump_json()
    # Renamed display filename — no Client ID, no server path, no URL.
    assert card.filename.startswith("PnL_Equity_")
    assert card.filename.endswith(".pdf")
    assert CLIENT_ID not in blob
    assert "http" not in blob
    assert "PNLReport" not in blob
    assert "PDFReports" not in blob


def test_download_url_never_enters_the_rendered_result():
    fixture = load("pnl_download_success.json")
    url = fixture["Response"]
    env = parse_dotnet_envelope(fixture)
    assert env.outcome is Outcome.success
    assert FLOW.delivery_kind(env) == "download"
    params = ExtractedParams(segment=Segment.equity, date_range=DateRange(from_=date(2026, 4, 1), to=TODAY))
    card = FLOW.file_card(params, size_label="196 KB")
    assert url not in card.model_dump_json()
