"""Flow events — the deterministic inputs ``advance`` dispatches on.

A ``FlowEvent`` is everything the engine needs to compute the next state without
free-text parsing: a chip selection, a calendar pick, a resend, a stepper reopen,
or a router-classified follow-up. The router owns turning free text / chip taps
into these; the engine owns what each does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.contracts.router import ExtractedParams


@dataclass(frozen=True)
class ParamSelected:
    """A ``select_param`` chip: a sparse ``ExtractedParams`` with just the chosen
    field set. The engine merges its non-``None`` fields into ``collected``."""

    update: ExtractedParams
    label: str | None = None


@dataclass(frozen=True)
class DateSelected:
    """A calendar pick — a from/to range for a ``date_range`` step."""

    from_: date
    to: date


@dataclass(frozen=True)
class Resend:
    """Explicit "send it again" / "resend" — re-generate, BYPASSING the cache."""


@dataclass(frozen=True)
class ReopenStep:
    """Tap a completed step to edit it — reopen and clear downstream selections."""

    step_id: str


@dataclass(frozen=True)
class FollowUp:
    """A router-classified follow-up turn. ``resolved`` is True when the follow-up
    disambiguated the request; unresolved follow-ups count against the cap."""

    resolved: bool = False


#: The events ``advance`` accepts.
FlowEvent = ParamSelected | DateSelected | Resend | ReopenStep | FollowUp
