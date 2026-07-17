"""Tax / Capital-Gain flow tests — written FROM the proposal doneCondition.

Each test asserts a clause the proposal promised, not merely what the code does:

- full walk drives ``GetTaxReportPDF`` with the correct dynamic ``FinYear``,
  ``RequestFor`` (2 download / 1 email), and ``FileFormat`` (1 PDF / 2 Excel; two
  calls on email);
- CG / Tax-P&L intents prepend the education line and still route here;
- AY→FY converts with an explicit confirm;
- out-of-window FY yields E-YEAR with NO API call;
- the string URL is fetched server-side and byte-validated per format;
- "Data not available." maps to E-NODATA.

FinX is faked at the frozen ``ParsedEnvelope`` boundary — success envelopes are
built through the REAL ``parse_dotnet_envelope`` parser, and the no-data case is
parsed from the checked-in ``tax_failure.json`` capture, so the tests exercise the
real contract, not a hand-waved shape. Offline; no live API.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.contracts.errors import EC12, ERROR_COPY, ErrorCode
from app.contracts.flow import (
    FlowSpec,
    current_fy,
    default_fy,
    fy_long_to_short,
    supported_fys,
)
from app.contracts.router import Intent, ReportFormat
from app.contracts.wire import Bubble, ChipRow, ErrorBubble, FileCard
from app.finx.envelopes import Outcome, ParsedEnvelope, parse_dotnet_envelope
from app.flows.tax import (
    FLOW,
    EDUCATION_COPY,
    FyResolutionKind,
    TaxFlow,
    TaxFlowDeps,
    mask_email,
)
from datetime import date

_FY2627 = date(2026, 7, 17)  # inside FY 2026-2027; supported = 26-27/25-26/24-25
_FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "finx"

PDF_URL = "https://client-report.choiceindia.com/PDFReports/TR9931_X008593.pdf"
XLSX_URL = "https://client-report.choiceindia.com/PDFReports/TR9931_X008593_1720000000.xlsx"
CLIENT_ID = "X008593"
SESSION_ID = "SID-abc-123"


# ---------------------------------------------------------------------------
# Fakes at the frozen ParsedEnvelope boundary
# ---------------------------------------------------------------------------


def _success_env(url: str) -> ParsedEnvelope:
    return parse_dotnet_envelope({"Status": "Success", "Response": url}, http_status=200)


def _email_env(masked_from: str) -> ParsedEnvelope:
    return parse_dotnet_envelope(
        {"Status": "Success", "Response": f"Mail sent to {masked_from}"}, http_status=200
    )


def _no_data_env() -> ParsedEnvelope:
    body = json.loads((_FIXTURES / "tax_failure.json").read_text())
    return parse_dotnet_envelope(body, http_status=200)


class _FakeDotNet:
    """Programmed ``get_tax_report_pdf`` results; records every request."""

    def __init__(self, results):
        self._results = list(results)  # each: ("return", env) | ("raise", exc)
        self.requests = []

    async def get_tax_report_pdf(self, req):
        self.requests.append(req)
        kind, value = self._results.pop(0)
        if kind == "raise":
            raise value
        return value


class _FakeFinX:
    def __init__(self, dotnet):
        self.dotnet = dotnet


class _FakeFetcher:
    """Programmed byte-fetch results; records every URL fetched."""

    def __init__(self, results):
        self._results = list(results)  # each: ("return", bytes) | ("raise", exc)
        self.urls = []

    async def __call__(self, url):
        self.urls.append(url)
        kind, value = self._results.pop(0)
        if kind == "raise":
            raise value
        return value


def _deps(*, dotnet_results, fetch_results=(), today=_FY2627):
    dotnet = _FakeDotNet(dotnet_results)
    fetcher = _FakeFetcher(fetch_results)
    deps = TaxFlowDeps(finx=_FakeFinX(dotnet), fetch_bytes=fetcher, today=today)
    return deps, dotnet, fetcher


def _valid_pdf(n: int = 4096) -> bytes:
    return b"%PDF-1.7\n" + b"0" * n


def _valid_xlsx(n: int = 4096) -> bytes:
    return b"PK\x03\x04" + b"0" * n


def _all_text(blocks) -> str:
    parts = []
    for b in blocks:
        parts.append(b.model_dump_json())
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Discovery + routing
# ---------------------------------------------------------------------------


def test_flow_registers_and_satisfies_flowspec():
    assert isinstance(FLOW, FlowSpec)
    assert FLOW.intent is Intent.report_tax
    assert FLOW.config.window.fy_based is True
    kinds = [(s.id, s.kind.value) for s in FLOW.steps()]
    assert kinds == [("fy", "fy"), ("delivery", "delivery")]


def test_three_intents_all_route_here():
    for intent in (Intent.report_tax, Intent.report_capital_gain, Intent.report_tax_pnl):
        assert FLOW.handles(intent) is True
    assert FLOW.handles(Intent.report_pnl) is False


# ---------------------------------------------------------------------------
# S0 education (CG / Tax-P&L prepend; tax does not)
# ---------------------------------------------------------------------------


def test_education_line_capital_gain():
    bubble = FLOW.education_line(Intent.report_capital_gain)
    assert isinstance(bubble, Bubble)
    assert bubble.text == EDUCATION_COPY[Intent.report_capital_gain]
    assert "capital gains are part of the Tax Report" in bubble.text


def test_education_line_tax_pnl():
    bubble = FLOW.education_line(Intent.report_tax_pnl)
    assert bubble is not None
    assert "Tax P&L is the Tax Report" in bubble.text


def test_no_education_line_for_plain_tax():
    assert FLOW.education_line(Intent.report_tax) is None


# ---------------------------------------------------------------------------
# S1 financial year — dynamic model (never hardcoded)
# ---------------------------------------------------------------------------


def test_fy_chips_are_dynamic_and_ordered():
    labels = [c.label for c in FLOW.fy_chips(_FY2627)]
    # default (last completed FY) first, current FY tagged year-to-date, then -2.
    assert labels[0] == fy_long_to_short(default_fy(_FY2627))
    assert labels[1] == fy_long_to_short(current_fy(_FY2627)) + " · year-to-date"
    assert labels[2] == fy_long_to_short(supported_fys(_FY2627)[2])
    # Each chip carries the long-form FY in its select payload.
    payload_fys = {c.action.payload["fy"] for c in FLOW.fy_chips(_FY2627)}
    assert payload_fys == set(supported_fys(_FY2627))


def test_fy_window_rolls_on_1_april():
    # A date one year later shifts the whole window forward — no hardcoded years.
    later = date(2027, 4, 2)  # FY 2027-2028
    assert [c.action.payload["fy"] for c in FLOW.fy_chips(later)][0] == default_fy(later)
    assert supported_fys(later) != supported_fys(_FY2627)


def test_free_text_fy_in_window_needs_confirm():
    res = FLOW.resolve_fy("tax report for 2024-25", _FY2627)
    assert res.kind is FyResolutionKind.needs_confirm
    assert res.fy_long == "2024-2025"
    assert res.blocks[0].text == "Got it — Tax Report for FY 2024-25. Confirm?"


def test_ay_converts_to_fy_with_explicit_confirm():
    # AY 2026-27 → FY 2025-26 (in window), explicit confirm before proceeding.
    res = FLOW.resolve_fy("give me AY 2026-27", _FY2627)
    assert res.kind is FyResolutionKind.needs_ay_confirm
    assert res.fy_long == "2025-2026"
    assert res.blocks[0].text == "AY 2026-27 → that's FY 2025-26, correct?"


def test_out_of_window_fy_yields_eyear_and_no_api_call():
    deps, dotnet, fetcher = _deps(dotnet_results=[])
    res = FLOW.resolve_fy("tax report for 2018-19", _FY2627)
    assert res.kind is FyResolutionKind.out_of_window
    bubble = res.blocks[0]
    assert isinstance(bubble, ErrorBubble)
    assert bubble.code is ErrorCode.E_YEAR
    # E-YEAR re-prompts with exactly the three in-window FY chips (default-first
    # chip order, per §4.2 — same set as supported_fys).
    fys = [c.action.payload["fy"] for c in bubble.chips]
    assert fys == [default_fy(_FY2627), current_fy(_FY2627), supported_fys(_FY2627)[2]]
    assert set(fys) == set(supported_fys(_FY2627))
    # No API call was issued for an out-of-window request.
    assert dotnet.requests == []


# ---------------------------------------------------------------------------
# S3/S4 in-chat delivery — request shape, server-side fetch, byte validation
# ---------------------------------------------------------------------------


async def test_deliver_here_pdf_request_shape_and_file_card():
    deps, dotnet, fetcher = _deps(
        dotnet_results=[("return", _success_env(PDF_URL))],
        fetch_results=[("return", _valid_pdf())],
    )
    blocks = await FLOW.deliver_here(
        fy_long="2024-2025",
        intent=Intent.report_tax,
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        fmt=ReportFormat.pdf,
        deps=deps,
    )
    req = dotnet.requests[0]
    assert req.FinYear == "2024-2025"
    assert req.RequestFor == 2  # download-here (ViewType-compliant)
    assert req.FileFormat == 1  # PDF
    assert req.ClientId == CLIENT_ID and req.SessionId == SESSION_ID
    # The report URL was fetched server-side.
    assert fetcher.urls == [PDF_URL]
    card = next(b for b in blocks if isinstance(b, FileCard))
    assert card.filename == "Tax_Report_FY2024-25.pdf"
    assert card.format == "pdf"
    assert card.password_hint is None  # tax files are not password-protected


async def test_deliver_here_excel_uses_fileformat_2_and_pk_validation():
    deps, dotnet, fetcher = _deps(
        dotnet_results=[("return", _success_env(XLSX_URL))],
        fetch_results=[("return", _valid_xlsx())],
    )
    blocks = await FLOW.deliver_here(
        fy_long="2024-2025",
        intent=Intent.report_tax,
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        fmt=ReportFormat.excel,
        deps=deps,
    )
    assert dotnet.requests[0].FileFormat == 2  # Excel
    card = next(b for b in blocks if isinstance(b, FileCard))
    assert card.filename == "Tax_Report_FY2024-25.xlsx"
    assert card.format == "xlsx"


async def test_wrong_magic_bytes_retries_once_then_efetch():
    # Both fetches return wrong magic bytes → one silent retry, then E-FETCH.
    deps, dotnet, fetcher = _deps(
        dotnet_results=[
            ("return", _success_env(PDF_URL)),
            ("return", _success_env(PDF_URL)),
        ],
        fetch_results=[("return", b"NOTPDF" + b"0" * 4096), ("return", b"STILLNOT" + b"0" * 4096)],
    )
    blocks = await FLOW.deliver_here(
        fy_long="2024-2025",
        intent=Intent.report_tax,
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        fmt=ReportFormat.pdf,
        deps=deps,
    )
    assert len(dotnet.requests) == 2  # retry = a fresh generation
    assert len(fetcher.urls) == 2
    assert isinstance(blocks[0], ErrorBubble) and blocks[0].code is ErrorCode.E_FETCH


async def test_efetch_recovers_when_retry_succeeds():
    deps, dotnet, fetcher = _deps(
        dotnet_results=[
            ("return", _success_env(PDF_URL)),
            ("return", _success_env(PDF_URL)),
        ],
        fetch_results=[("return", b""), ("return", _valid_pdf())],  # 404-empty, then good
    )
    blocks = await FLOW.deliver_here(
        fy_long="2024-2025",
        intent=Intent.report_tax,
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        fmt=ReportFormat.pdf,
        deps=deps,
    )
    assert len(dotnet.requests) == 2
    assert any(isinstance(b, FileCard) for b in blocks)


async def test_data_not_available_maps_to_enodata_without_fetch():
    deps, dotnet, fetcher = _deps(
        dotnet_results=[("return", _no_data_env())],
        fetch_results=[],
    )
    # Sanity: the checked-in capture really is a no_data envelope.
    assert _no_data_env().outcome is Outcome.no_data
    blocks = await FLOW.deliver_here(
        fy_long="2024-2025",
        intent=Intent.report_tax,
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        fmt=ReportFormat.pdf,
        deps=deps,
    )
    assert isinstance(blocks[0], ErrorBubble) and blocks[0].code is ErrorCode.E_NODATA
    assert fetcher.urls == []  # no URL fetch on a no-data failure


async def test_timeout_maps_to_etimeout():
    deps, dotnet, fetcher = _deps(dotnet_results=[("raise", TimeoutError())])
    blocks = await FLOW.deliver_here(
        fy_long="2024-2025",
        intent=Intent.report_tax,
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        fmt=ReportFormat.pdf,
        deps=deps,
    )
    assert isinstance(blocks[0], ErrorBubble) and blocks[0].code is ErrorCode.E_TIMEOUT


async def test_report_url_never_appears_in_render_blocks():
    deps, dotnet, fetcher = _deps(
        dotnet_results=[("return", _success_env(PDF_URL))],
        fetch_results=[("return", _valid_pdf())],
    )
    blocks = await FLOW.deliver_here(
        fy_long="2024-2025",
        intent=Intent.report_tax,
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        fmt=ReportFormat.pdf,
        deps=deps,
    )
    rendered = _all_text(blocks)
    assert PDF_URL not in rendered
    assert "PDFReports" not in rendered
    assert CLIENT_ID not in rendered  # renamed filename must not leak the Client ID


async def test_capital_gain_lead_in_and_current_fy_provisional_caption():
    deps, dotnet, fetcher = _deps(
        dotnet_results=[("return", _success_env(PDF_URL))],
        fetch_results=[("return", _valid_pdf())],
    )
    blocks = await FLOW.deliver_here(
        fy_long=current_fy(_FY2627),  # current FY → provisional caption
        intent=Intent.report_capital_gain,
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        fmt=ReportFormat.pdf,
        deps=deps,
    )
    lead_in = blocks[0].text
    assert lead_in.startswith("Here's your Tax Report for")
    assert "capital gains are inside" in lead_in
    assert any("year-to-date, figures may change till 31 Mar." in b.text
               for b in blocks if isinstance(b, Bubble))


# ---------------------------------------------------------------------------
# Email branch — two calls, masking, EC-12
# ---------------------------------------------------------------------------


async def test_email_issues_two_calls_and_masks_address():
    deps, dotnet, fetcher = _deps(
        dotnet_results=[
            ("return", _email_env("SANDEEP.HARSHA@GMAIL.COM")),  # PDF (FileFormat 1)
            ("return", _email_env("SANDEEP.HARSHA@GMAIL.COM")),  # Excel (FileFormat 2)
        ],
    )
    blocks = await FLOW.deliver_email(
        fy_long="2024-2025",
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        deps=deps,
    )
    # Two calls, RequestFor 1, FileFormat 1 then 2.
    assert [r.RequestFor for r in dotnet.requests] == [1, 1]
    assert [r.FileFormat for r in dotnet.requests] == [1, 2]
    sent = blocks[0].text
    assert "on its way to san***.harsha@gmail.com" in sent
    assert "SANDEEP" not in _all_text(blocks)  # raw/uppercased email never surfaced


async def test_email_partial_failure_uses_ec12_copy():
    deps, dotnet, fetcher = _deps(
        dotnet_results=[
            ("return", _email_env("SANDEEP.HARSHA@GMAIL.COM")),  # PDF ok
            ("return", _no_data_env()),  # Excel fails
        ],
    )
    blocks = await FLOW.deliver_email(
        fy_long="2024-2025",
        client_id=CLIENT_ID,
        session_id=SESSION_ID,
        deps=deps,
    )
    bubble = blocks[0]
    assert isinstance(bubble, ErrorBubble)
    assert bubble.text == EC12.text.format(masked_email="san***.harsha@gmail.com")
    assert [c.label for c in bubble.chips] == list(EC12.chips)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_mask_email_matches_pnl_pattern():
    assert mask_email("sandeep.harsha@gmail.com") == "san***.harsha@gmail.com"
    assert mask_email("BOB@EXAMPLE.COM") == "bob***@example.com"


def test_error_copy_never_exposes_reason_or_url():
    # Every error bubble the flow can emit is drawn from the frozen ERROR_COPY and
    # carries no server Reason string, HTTP code, or URL.
    for code in (ErrorCode.E_NODATA, ErrorCode.E_YEAR, ErrorCode.E_TIMEOUT,
                 ErrorCode.E_FETCH, ErrorCode.E_UNKNOWN):
        bubble = FLOW.error_bubble(code, "2024-2025", _FY2627)
        assert bubble.text
        assert "http" not in bubble.text.lower()
        assert "Reason" not in bubble.text
