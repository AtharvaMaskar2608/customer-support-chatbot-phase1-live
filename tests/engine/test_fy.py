"""T4: financial-year resolution via the frozen FY helpers (proposal §FY helper use)."""

from __future__ import annotations

from datetime import date

from app.contracts.flow import supported_fys
from app.contracts.router import ExtractedParams

from app.engine.fy import normalize_fy, resolve_fy
from app.engine.results import EYearError, FYResolved

TODAY = date(2026, 7, 17)  # FY 2026-2027; supported = 2026-27, 2025-26, 2024-25


def test_in_window_long_form_resolves():
    got = resolve_fy(ExtractedParams(fy="2025-2026"), TODAY)
    assert isinstance(got, FYResolved) and got.fy_long == "2025-2026"


def test_short_form_is_normalized():
    assert normalize_fy("FY 2025-26") == "2025-2026"
    assert normalize_fy("2025-26") == "2025-2026"
    got = resolve_fy(ExtractedParams(fy="FY 2024-25"), TODAY)
    assert isinstance(got, FYResolved) and got.fy_long == "2024-2025"


def test_out_of_window_yields_eyear_with_supported_chips_no_api_call():
    got = resolve_fy(ExtractedParams(fy="2020-2021"), TODAY)
    assert isinstance(got, EYearError)
    assert got.requested == "2020-2021"
    # The three in-window FYs travel with the error for the recovery chips.
    assert got.supported == tuple(supported_fys(TODAY))
    # resolve_fy is pure — it takes no adapter and makes no call by construction.


def test_missing_fy_yields_eyear():
    got = resolve_fy(ExtractedParams(fy=None), TODAY)
    assert isinstance(got, EYearError) and got.requested is None


def test_unparseable_fy_yields_eyear_not_crash():
    got = resolve_fy(ExtractedParams(fy="last year"), TODAY)
    assert isinstance(got, EYearError) and got.requested == "last year"


def test_years_never_hardcoded_far_future():
    future = date(2099, 5, 1)  # FY 2099-2100
    ok = resolve_fy(ExtractedParams(fy="2098-2099"), future)
    assert isinstance(ok, FYResolved) and ok.fy_long == "2098-2099"
    stale = resolve_fy(ExtractedParams(fy="2024-2025"), future)
    assert isinstance(stale, EYearError)  # rolled out of the window
