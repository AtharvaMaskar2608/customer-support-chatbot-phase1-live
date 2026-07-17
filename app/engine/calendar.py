"""Per-flow date-window enforcement (proposal §Per-flow date-window; 02 §2.5/§8.3).

Each flow's frozen ``DateWindow`` (floor, ``cap_relative_days``, ``max_range_years``)
drives an in-chat calendar whose out-of-range dates are HARD-DISABLED (bounds are
set so the widget cannot select them — never validate-after). ``validate_range`` is
the defensive belt-and-suspenders reject for an out-of-range selection. Windows are
NOT unified: every value comes from that flow's own config.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.contracts.wire import Bubble, Calendar

from app.engine.ports import FlowDefinition


def add_years(d: date, years: int) -> date:
    """``d`` plus ``years`` calendar years, clamping 29 Feb → 28 Feb. Used for the
    exact (leap-safe) ``max_range_years`` span clamp the spec states in years."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def _cap_date(window, today: date) -> date:
    cap_days = window.cap_relative_days if window.cap_relative_days is not None else 0
    return today + timedelta(days=cap_days)


def build_calendar(flow: FlowDefinition, today: date) -> Calendar:
    """The in-chat calendar for a date-range flow. ``min_date``/``max_date`` bound
    the selectable window (out-of-range dates are unselectable); ``max_range_days``
    is a widget hint derived from the flow's ``max_range_years``."""
    w = flow.config.window
    if w.fy_based:
        raise ValueError("fy_based flows use FY selection, not a calendar")
    if w.floor is None:
        raise ValueError("a calendar flow requires a window floor")

    max_range_days: int | None = None
    if w.max_range_years is not None:
        max_range_days = (add_years(today, w.max_range_years) - today).days

    return Calendar(
        min_date=w.floor,
        max_date=_cap_date(w, today),
        disabled_ranges=[],  # no interior holes; the bounds do the hard-disabling
        max_range_days=max_range_days,
    )


def validate_range(
    flow: FlowDefinition,
    from_: date | None,
    to: date | None,
    *,
    today: date | None = None,
) -> bool:
    """Defensive reject of an out-of-range selection. True only when the selection
    sits inside this flow's floor / today-relative cap and within the exact
    (leap-safe) ``max_range_years`` span."""
    today = today or date.today()
    w = flow.config.window
    if w.fy_based:
        return False  # fy flows carry no date range
    if from_ is None or to is None or from_ > to:
        return False
    if w.floor is not None and from_ < w.floor:
        return False
    if to > _cap_date(w, today):
        return False
    if w.max_range_years is not None and to > add_years(from_, w.max_range_years):
        return False
    return True


def out_of_range_nudge(flow: FlowDefinition, today: date | None = None) -> Bubble:
    """The nudge shown if an out-of-range selection somehow reaches the backend.
    Engine-default copy (no frozen taxonomy entry for a range nudge); a flow may
    override via a ``range_nudge`` attribute. [CONFIRM: final flow-owned copy]"""
    override = getattr(flow, "range_nudge", None)
    if isinstance(override, str):
        return Bubble(text=override)
    today = today or date.today()
    w = flow.config.window
    lo = w.floor.isoformat() if w.floor else "the earliest available date"
    hi = _cap_date(w, today).isoformat()
    span = f" (up to {w.max_range_years} years at a time)" if w.max_range_years else ""
    return Bubble(text=f"Please pick dates between {lo} and {hi}{span}.")
