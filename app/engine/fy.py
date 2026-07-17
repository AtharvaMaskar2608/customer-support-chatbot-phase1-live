"""Financial-year resolution (proposal §FY helper use).

Resolves a requested financial year against the rolling in-window set using the
FROZEN FY helpers in ``app.contracts.flow`` — the engine imports them and NEVER
reimplements the Apr-1 rollover or hardcodes the three years. An out-of-window FY
resolves to ``EYearError`` BEFORE any generation/adapter call.
"""

from __future__ import annotations

from datetime import date

from app.contracts.flow import fy_short_to_long, supported_fys
from app.contracts.router import ExtractedParams

from app.engine.results import EYearError, FYResolved


def normalize_fy(raw: str) -> str:
    """Coerce a requested FY into the API long form ``"YYYY-YYYY"``. Accepts the
    long form, the short chip form (``"FY 2025-26"``), and the bare short form
    (``"2025-26"``). Raises ``ValueError`` on anything unparseable."""
    s = raw.strip()
    if s.upper().startswith("FY"):
        return fy_short_to_long(s)
    parts = s.split("-")
    if len(parts) == 2 and len(parts[1].strip()) == 2:
        return fy_short_to_long(f"FY {s}")
    if len(parts) == 2 and len(parts[0].strip()) == 4 and len(parts[1].strip()) == 4:
        return s  # already long form
    raise ValueError(f"unparseable financial year: {raw!r}")


def resolve_fy(params: ExtractedParams, today: date | None = None) -> FYResolved | EYearError:
    """Resolve ``params.fy`` against ``supported_fys(today)`` (currentFY + last two).
    In-window → ``FYResolved`` (long form). Missing, out-of-window, or unparseable →
    ``EYearError`` carrying the supported set for the three recovery chips. No
    adapter call is made either way (pure)."""
    today = today or date.today()
    supported = tuple(supported_fys(today))

    if not params.fy:
        return EYearError(requested=None, supported=supported)

    try:
        fy_long = normalize_fy(params.fy)
    except ValueError:
        return EYearError(requested=params.fy, supported=supported)

    if fy_long in supported:
        return FYResolved(fy_long=fy_long)
    return EYearError(requested=fy_long, supported=supported)
