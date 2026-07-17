"""T7: error-taxonomy mapping (proposal §Error-code mapping; 02 §8.4)."""

from __future__ import annotations

from app.contracts.errors import ERROR_COPY, ErrorCode
from app.contracts.flow import fy_long_to_short, supported_fys
from app.contracts.router import ExtractedParams
from app.contracts.wire import ChipActionKind

from app.engine.errors import map_error
from app.engine.faults import FinXAuthError, FinXFetchError, FinXTimeoutError, FinXTransportError
from app.engine.ports import GenerationError, NoData
from app.engine.results import EYearError
from tests.engine.conftest import make_ctx

CTX = make_ctx()  # now = 2026-07-17 → supported FYs 2026-27, 2025-26, 2024-25


def test_nodata_verbatim_with_fy_substitution():
    bubble = map_error(NoData(reason="Data not found."), ctx=CTX, params=ExtractedParams(fy="2024-2025"))
    assert bubble.code is ErrorCode.E_NODATA
    assert bubble.text == "No transactions found for FY 2024-25, so there's nothing to report for that year."
    # First chip re-selects the default FY (verbatim label + typed fy payload).
    assert bubble.chips[0].label == "Try FY 2025-26 (or another in-window year)"
    assert bubble.chips[0].action.kind is ChipActionKind.select_param
    assert bubble.chips[0].action.payload == {"fy": "2025-2026"}
    assert bubble.chips[1].label == "🎫 Raise a ticket"
    assert bubble.chips[1].action.kind is ChipActionKind.raise_ticket


def test_eyear_renders_three_dynamic_fy_chips():
    err = EYearError(requested="2020-2021", supported=tuple(supported_fys(CTX.now.date())))
    bubble = map_error(err, ctx=CTX)
    assert bubble.code is ErrorCode.E_YEAR
    assert bubble.text == "I can pull Tax Reports for the current and last two financial years — that's FY 2026-27, FY 2025-26 and FY 2024-25. Which one?"
    assert [c.label for c in bubble.chips] == [fy_long_to_short(f) for f in supported_fys(CTX.now.date())]
    assert [c.action.payload["fy"] for c in bubble.chips] == list(supported_fys(CTX.now.date()))
    assert all(c.action.kind is ChipActionKind.select_param for c in bubble.chips)


def test_timeout_verbatim_preserves_selections_copy():
    bubble = map_error(FinXTimeoutError("read timeout on http://finx/..."), ctx=CTX)
    assert bubble.code is ErrorCode.E_TIMEOUT
    assert bubble.text == ERROR_COPY[ErrorCode.E_TIMEOUT].text
    assert "Your selections are saved." in bubble.text
    assert [c.label for c in bubble.chips] == ["↺ Retry", "🎫 Raise a ticket"]


def test_fetch_surfaces_second_line():
    bubble = map_error(FinXFetchError("magic byte mismatch"), ctx=CTX)
    assert bubble.code is ErrorCode.E_FETCH
    assert bubble.text == ERROR_COPY[ErrorCode.E_FETCH].second_line == "Still not coming through cleanly."
    assert [c.label for c in bubble.chips] == ["↺ Try again", "✉️ Email me both", "🎫 Raise a ticket"]
    kinds = [c.action.kind for c in bubble.chips]
    assert kinds == [ChipActionKind.retry, ChipActionKind.email, ChipActionKind.raise_ticket]


def test_unknown_covers_generation_auth_and_transport():
    for fault in (GenerationError(reason="Status: Weird"), FinXAuthError("401"), FinXTransportError("502")):
        bubble = map_error(fault, ctx=CTX)
        assert bubble.code is ErrorCode.E_UNKNOWN
        assert bubble.text == ERROR_COPY[ErrorCode.E_UNKNOWN].text


def test_copy_never_leaks_reason_url_or_http_code():
    leaky = FinXFetchError("404 at https://client-report.choiceindia.com/PDFReports/secret.pdf reason=Invalid SessionId")
    bubble = map_error(leaky, ctx=CTX)
    for secret in ("http", "404", "SessionId", "Invalid", "PDFReports"):
        assert secret not in bubble.text
