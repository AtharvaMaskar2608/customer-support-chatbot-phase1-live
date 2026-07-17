"""Flow/step state-machine contract (flow-engine-contract capability).

Defines the flow/step state-machine types the engine drives, per-flow date-window
config (values live in remote-config), the byte-validation / one-silent-retry /
15-minute cache semantics as typed config, and the ``FlowSpec`` protocol + the
module-level ``FLOW`` registration contract (D6). The financial-year helpers are
IMPLEMENTED here (D13) — shared by the engine, the tax flow, and the router so the
Apr-1 rollover logic exists exactly once and never hardcodes the three years.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Protocol, Sequence, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.router import ExtractedParams, Intent

# ---------------------------------------------------------------------------
# Financial-year helpers (IMPLEMENTED, not merely typed — D13)
# ---------------------------------------------------------------------------


def current_fy(today: date | None = None) -> str:
    """The current financial year as ``"YYYY-YYYY"``. The start year is
    ``today.year`` when ``today.month >= 4`` (on/after 1 April), else
    ``today.year - 1``. Computed dynamically — never hardcoded."""
    today = today or date.today()
    start = today.year if today.month >= 4 else today.year - 1
    return f"{start}-{start + 1}"


def _fy_start_year(fy_long: str) -> int:
    return int(fy_long.split("-")[0])


def supported_fys(today: date | None = None) -> list[str]:
    """``[currentFY, currentFY-1, currentFY-2]`` in long ``"YYYY-YYYY"`` form.
    Rolls forward on 1 April so the oldest year drops without a code change."""
    start = _fy_start_year(current_fy(today))
    return [f"{y}-{y + 1}" for y in (start, start - 1, start - 2)]


def default_fy(today: date | None = None) -> str:
    """``currentFY - 1`` — the last completed FY, pre-highlighted and listed
    first on the tax-flow chips."""
    start = _fy_start_year(current_fy(today)) - 1
    return f"{start}-{start + 1}"


def fy_long_to_short(fy_long: str) -> str:
    """``"2025-2026"`` → ``"FY 2025-26"`` (the short chip form)."""
    start = _fy_start_year(fy_long)
    return f"FY {start}-{str(start + 1)[-2:]}"


def fy_short_to_long(fy_short: str) -> str:
    """``"FY 2025-26"`` → ``"2025-2026"`` (the API long form)."""
    body = fy_short.replace("FY", "").strip()
    start = int(body.split("-")[0].strip())
    return f"{start}-{start + 1}"


# ---------------------------------------------------------------------------
# Step / flow state machine
# ---------------------------------------------------------------------------


class StepKind(str, Enum):
    """A step's kind determines which render block the engine emits (e.g.
    ``date_range`` → calendar, ``segment`` → chip row)."""

    segment = "segment"
    date_range = "date_range"
    fy = "fy"
    delivery = "delivery"
    format = "format"
    confirm = "confirm"
    generate = "generate"


class StepState(str, Enum):
    pending = "pending"
    active = "active"
    done = "done"


class Step(BaseModel):
    """One flow step. Completed steps stay editable; reopening a done step clears
    downstream selections."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: StepKind
    state: StepState = StepState.pending
    selected_label: str | None = None


class TransitionKind(str, Enum):
    advance = "advance"  # move to the next step
    edit_reopen = "edit_reopen"  # tap a done step → reopen, clear downstream
    complete = "complete"  # flow reaches generation


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TransitionKind
    from_step: str
    to_step: str


class FlowState(BaseModel):
    """The engine's per-flow state — enough to resume deterministically."""

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    current_step: StepKind
    collected: ExtractedParams = Field(default_factory=ExtractedParams)
    cache_key: str | None = None
    steps: list[Step] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-flow date-window config (values live in remote-config; type lives here)
# ---------------------------------------------------------------------------


class DateWindow(BaseModel):
    """A flow's calendar bounds. The engine hard-disables out-of-range dates in
    the calendar rather than validating after selection. ``cap_relative_days`` is
    an offset from today (e.g. 7 → today+7, 0 → today). ``fy_based`` flows (Tax)
    use FY selection, not a date range."""

    model_config = ConfigDict(extra="forbid")

    floor: date | None = None
    cap_relative_days: int | None = None
    max_range_days: int | None = None
    fy_based: bool = False


class FlowConfig(BaseModel):
    """Per-flow configuration the engine reads (window from remote-config)."""

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    window: DateWindow


# ---------------------------------------------------------------------------
# Byte-validation, retry, and cache semantics (typed config)
# ---------------------------------------------------------------------------

#: Magic bytes checked before every file delivery.
PDF_MAGIC: bytes = b"%PDF"
EXCEL_MAGIC: bytes = b"PK"  # zip header
MAGIC_BYTES: dict[str, bytes] = {"pdf": PDF_MAGIC, "xlsx": EXCEL_MAGIC}


class ByteValidation(BaseModel):
    """Size-floor + magic-byte validation applied before every file delivery. On
    failure the engine performs exactly one silent auto-retry with a fresh
    generation; only if the retry also fails does it surface the E-FETCH bubble."""

    model_config = ConfigDict(extra="forbid")

    min_bytes: int = 1024
    pdf_magic: bytes = PDF_MAGIC
    excel_magic: bytes = EXCEL_MAGIC
    silent_retries: int = 1  # exactly one silent auto-retry


class CacheConfig(BaseModel):
    """Per-flow byte/selection cache: 15-minute TTL, session-scoped, keyed per
    selection so edits do not cross-contaminate. Explicit "send it again" /
    "resend" bypasses the cache and forces a fresh fetch."""

    model_config = ConfigDict(extra="forbid")

    ttl_seconds: int = 900  # 15 minutes
    bypass_on_resend: bool = True


def selection_cache_key(intent: Intent, params: ExtractedParams) -> str:
    """A cache key that changes when any selection changes, so a prior
    selection's cached bytes are never reused after an edit."""
    return f"{intent.value}:{params.model_dump_json()}"


# ---------------------------------------------------------------------------
# Flow registration contract (module-level FLOW; discovery owned by change 2)
# ---------------------------------------------------------------------------

#: The module-level attribute the engine's importlib discovery reads. Each flow
#: module exposes ``FLOW: FlowSpec`` and imports NO registration function; there
#: is no register decorator and no hand-maintained shared registry list (D6).
FLOW_ATTR: str = "FLOW"


@runtime_checkable
class FlowSpec(Protocol):
    """The contract a flow module's module-level ``FLOW`` object satisfies. Kept
    minimal and stable: its ``intent`` keys the discovery registry; ``config``
    carries the flow's window; ``steps()`` yields the flow's ordered steps."""

    intent: Intent
    config: FlowConfig

    def steps(self) -> Sequence[Step]: ...
