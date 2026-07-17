"""T3: per-flow date-window enforcement (proposal §Per-flow date-window)."""

from __future__ import annotations

from datetime import date

from app.contracts.flow import DateWindow
from app.contracts.router import Intent

from app.engine.calendar import add_years, build_calendar, out_of_range_nudge, validate_range
from tests.engine.conftest import FakeFlow

TODAY = date(2026, 7, 17)


def _pnl():  # floor 2018-01-01, cap = today, 2-year max range
    return FakeFlow(intent=Intent.report_pnl, window=DateWindow(floor=date(2018, 1, 1), cap_relative_days=0, max_range_years=2))


def _ledger():  # floor 2019-01-01, cap = today+7, no max range
    return FakeFlow(intent=Intent.report_ledger, window=DateWindow(floor=date(2019, 1, 1), cap_relative_days=7, max_range_years=None))


def test_build_calendar_honors_flow_floor_and_cap():
    cal = build_calendar(_pnl(), TODAY)
    assert cal.min_date == date(2018, 1, 1)
    assert cal.max_date == TODAY  # cap_relative_days = 0

    lcal = build_calendar(_ledger(), TODAY)
    assert lcal.min_date == date(2019, 1, 1)
    assert lcal.max_date == date(2026, 7, 24)  # today + 7
    assert lcal.max_range_days is None  # ledger has no span clamp


def test_windows_are_not_unified():
    assert build_calendar(_pnl(), TODAY).min_date != build_calendar(_ledger(), TODAY).min_date
    assert build_calendar(_pnl(), TODAY).max_date != build_calendar(_ledger(), TODAY).max_date


def test_max_range_days_hint_is_leap_exact():
    # 2026-07-17 + 2y = 2028-07-17; the span includes 29 Feb 2028 → 731 days.
    assert build_calendar(_pnl(), TODAY).max_range_days == 731
    assert add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)  # 29 Feb clamps


def test_validate_range_in_window_true():
    assert validate_range(_pnl(), date(2024, 4, 1), date(2024, 6, 30), today=TODAY) is True


def test_validate_range_rejects_before_floor_and_after_cap():
    assert validate_range(_pnl(), date(2017, 12, 31), date(2018, 6, 30), today=TODAY) is False
    assert validate_range(_pnl(), date(2026, 7, 1), date(2026, 7, 18), today=TODAY) is False  # to > cap (today)


def test_validate_range_exact_year_clamp_across_leap():
    # from 2024-01-01, 2-year clamp → to must be <= 2026-01-01 exactly.
    flow = _pnl()
    assert validate_range(flow, date(2024, 1, 1), date(2026, 1, 1), today=date(2026, 7, 1)) is True
    assert validate_range(flow, date(2024, 1, 1), date(2026, 1, 2), today=date(2026, 7, 1)) is False


def test_validate_range_rejects_inverted_and_fy_flows():
    assert validate_range(_pnl(), date(2024, 6, 30), date(2024, 4, 1), today=TODAY) is False  # from > to
    tax = FakeFlow(intent=Intent.report_tax, window=DateWindow(fy_based=True))
    assert validate_range(tax, date(2024, 4, 1), date(2024, 6, 30), today=TODAY) is False


def test_build_calendar_rejects_fy_based_flow():
    tax = FakeFlow(intent=Intent.report_tax, window=DateWindow(fy_based=True))
    try:
        build_calendar(tax, TODAY)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("fy_based flow has no calendar")


def test_out_of_range_nudge_is_generic_and_flow_overridable():
    nudge = out_of_range_nudge(_pnl(), TODAY)
    assert "2018-01-01" in nudge.text and "2026-07-17" in nudge.text
    flow = _pnl()
    flow.range_nudge = "Pick a date in the last 2 FYs."
    assert out_of_range_nudge(flow, TODAY).text == "Pick a date in the last 2 FYs."
