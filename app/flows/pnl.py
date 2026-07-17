"""P&L Statement flow (flow-pnl capability — spec §8, owner variant 2a).

A self-contained ``FlowDefinition`` for the highest-volume report request. The
LLM only classifies intent + extracts params; a deterministic stepper drives
**Segment → Date range → Delivery**, then the engine calls ``GetGlobalPNLPDF``
server-side and delivers a byte-validated PDF file card (password: PAN) or a
masked-email confirmation.

Ownership split (see ``05_parallelization_plan.md`` + ``flow-engine-runtime``):
this module owns only P&L-specific declarations and render/request builders
against the FROZEN contracts (``app/contracts/**``, ``app/finx/**``). The generic
mechanics — the state-machine executor, step progression, the byte-fetch +
one-silent-retry loop, the 15-minute cache, and the authoritative calendar /
delivery / error assembly — are owned by ``flow-engine-runtime`` and integrated
in Wave 2. Discovery is by the module-level ``FLOW`` attribute (importlib
registry in ``app/flows/__init__.py``); this module adds no registration import.

Security invariants (spec §2.6, plan §3.7): the FinX report URL, ``file_id`` and
the server filename are fetched server-side and NEVER placed in a render block or
a log. Render blocks here carry only display-safe fields; the display filename is
renamed so it cannot leak the Client ID. Error copy is IMPORTED verbatim from the
frozen ``error-taxonomy`` — never redefined — and ``Reason`` strings, HTTP codes,
and URLs never reach user copy.
"""

from __future__ import annotations

import calendar as _calendar
import re
from datetime import date, timedelta
from enum import Enum
from typing import Sequence

from app.contracts.errors import ERROR_COPY, ErrorCode
from app.contracts.flow import DateWindow, FlowConfig, Step, StepKind
from app.contracts.router import Delivery, ExtractedParams, Intent, Segment
from app.contracts.wire import (
    Bubble,
    Calendar,
    Chip,
    ChipAction,
    ChipActionKind,
    ChipRow,
    ErrorBubble,
    FileCard,
    Generating,
)
from app.finx.envelopes import Outcome, ParsedEnvelope
from app.finx.models import FileDeliveryResponse, PnlPdfRequest

# ---------------------------------------------------------------------------
# P&L-specific constant maps (the identity/vocabulary traps live here)
# ---------------------------------------------------------------------------

#: Customer-facing segment → the ``GetGlobalPNLPDF`` ``Group`` value. NEVER surface
#: ``Cash``/``Derv``/``Comm`` to a customer ("Derv" is jargon that must not leak).
SEGMENT_GROUP: dict[Segment, str] = {
    Segment.equity: "Cash",
    Segment.fno: "Derv",
    Segment.commodity: "Comm",
}

#: Customer-facing labels for the segment chips / captions.
SEGMENT_LABEL: dict[Segment, str] = {
    Segment.equity: "Equity",
    Segment.fno: "F&O",
    Segment.commodity: "Commodity",
}

#: Filesystem-safe segment token for the renamed display filename.
SEGMENT_FILE_TOKEN: dict[Segment, str] = {
    Segment.equity: "Equity",
    Segment.fno: "FnO",
    Segment.commodity: "Commodity",
}

#: ``RequestFor`` is per-endpoint on ``GetGlobalPNLPDF``: 0 = download, 1 = email.
#: (Do NOT reuse a shared enum — Tax uses 2 for download.)
REQUEST_FOR: dict[Delivery, int] = {Delivery.in_chat: 0, Delivery.email: 1}

# Per-flow date window (spec §2.5 / §8.3): floor 2018-01-01, cap today+7, 2-year
# max-range clamp. Values are declared on the flow config; the engine enforces
# them (hard-disabled calendar dates) — the flow never validates-after.
FLOOR: date = date(2018, 1, 1)
CAP_RELATIVE_DAYS: int = 7
MAX_RANGE_YEARS: int = 2

#: PDF password is the client's PAN (spec §8.3).
PASSWORD_HINT: str = "PAN"

# Flow-owned copy (the engine emits SHARED error-taxonomy copy; per-flow nudge /
# ack / caption / confirmation copy is the flow's — see flow-engine-runtime).
NUDGE_FLOOR: str = "I can fetch your P&L from Jan 2018 onwards — pick a start date from then."
NUDGE_CAP: str = "I can't pull a P&L for a future date — pick an end date on or before today."
NUDGE_RANGE: str = (
    "P&L covers up to a 2-year range at a time — pick an end date within two years "
    "of your start date."
)


class DatePreset(str, Enum):
    """The four date-range chips (spec §8.3). ``custom`` opens the calendar."""

    this_fy = "this_fy"
    this_month = "this_month"
    last_3_months = "last_3_months"
    custom = "custom"


# ---------------------------------------------------------------------------
# Small date helpers (P&L presets + the exact 2-year clamp)
# ---------------------------------------------------------------------------


def _add_years(d: date, n: int) -> date:
    """``d`` + ``n`` calendar years, clamping 29 Feb → 28 Feb on non-leap years."""
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 Feb → non-leap target year
        return d.replace(year=d.year + n, day=28)


def _subtract_months(d: date, n: int) -> date:
    month = d.month - n
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    last = _calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last))


def _fmt(d: date) -> str:
    """Human date, e.g. ``1 Apr 2026`` (no platform-specific ``%-d``)."""
    return f"{d.day} {d:%b} {d.year}"


def _fy_short_for_range(from_: date, to: date) -> str | None:
    """``"FY2025-26"`` when the range is a clean financial year (1 Apr → within
    that FY), else ``None`` — used only for the display filename / caption."""
    if from_.month == 4 and from_.day == 1:
        fy_end = _add_years(from_, 1) - timedelta(days=1)  # 31 Mar next year
        if from_ <= to <= fy_end:
            return f"FY{from_.year}-{str(from_.year + 1)[-2:]}"
    return None


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[\w.-]+")


def mask_registered_email(response: str | None) -> str:
    """Mask the registered email leaked (uppercased) by the polymorphic email
    ``Response`` before any display, e.g.
    ``SANJAY.HARSHA@GMAIL.COM`` → ``san***.harsha@gmail.com`` (spec §4.1).

    Keeps the first three local-part chars and the tail from the last dot,
    masking the middle; the domain is preserved (lower-cased). Falls back to a
    generic phrase when no address is present."""
    match = _EMAIL_RE.search(response or "")
    if not match:
        return "your registered email"
    local, _, domain = match.group(0).strip().lower().partition("@")
    if not domain:
        return "your registered email"
    if len(local) <= 3:
        masked_local = (local[0] if local else "") + "***"
    else:
        dot = local.rfind(".")
        masked_local = local[:3] + "***" + local[dot:] if dot > 3 else local[:3] + "***"
    return f"{masked_local}@{domain}"


# ---------------------------------------------------------------------------
# Chip / render helpers
# ---------------------------------------------------------------------------


def _chip(label: str, kind: ChipActionKind, **payload: str) -> Chip:
    return Chip(label=label, action=ChipAction(kind=kind, payload=payload))


def _recovery_chip(label: str) -> Chip:
    """Map a frozen recovery-chip label to a typed chip action (labels are
    rendered verbatim; only the action kind is inferred)."""
    low = label.lower()
    if "raise a ticket" in low:
        kind = ChipActionKind.raise_ticket
    elif "call" in low:
        kind = ChipActionKind.call_support
    elif "email" in low:
        kind = ChipActionKind.email
    elif "log in" in low:
        kind = ChipActionKind.deep_link
    elif any(w in low for w in ("retry", "try again", "send it again", "resend")):
        kind = ChipActionKind.retry
    elif "fy" in low or "in-window year" in low:
        kind = ChipActionKind.select_param
    else:
        kind = ChipActionKind.send_text
    return _chip(label, kind)


def _safe_format(text: str, subs: dict[str, str]) -> str:
    for key, value in subs.items():
        text = text.replace("{" + key + "}", value)
    return text


# ---------------------------------------------------------------------------
# The flow definition (module-level ``FLOW`` satisfies the frozen FlowSpec)
# ---------------------------------------------------------------------------


class PnlFlow:
    """The P&L ``FlowDefinition``. Satisfies the frozen ``FlowSpec`` protocol
    (``intent`` / ``config`` / ``steps()``) for discovery, and carries the
    P&L-specific request + render builders the engine invokes at integration."""

    intent: Intent = Intent.report_pnl
    config: FlowConfig = FlowConfig(
        intent=Intent.report_pnl,
        window=DateWindow(
            floor=FLOOR,
            cap_relative_days=CAP_RELATIVE_DAYS,
            max_range_years=MAX_RANGE_YEARS,
        ),
    )
    password_hint: str = PASSWORD_HINT
    report_format: str = "pdf"  # PDF only — no FileFormat field on this endpoint

    # -- steps -------------------------------------------------------------
    def steps(self) -> Sequence[Step]:
        """Ordered steps: Segment → Date range → Delivery."""
        return [
            Step(id="segment", kind=StepKind.segment),
            Step(id="date_range", kind=StepKind.date_range),
            Step(id="delivery", kind=StepKind.delivery),
        ]

    # -- FinX request ------------------------------------------------------
    def group_for(self, segment: Segment) -> str:
        return SEGMENT_GROUP[segment]

    def resolve_preset(self, preset: DatePreset, *, today: date | None = None):
        """Resolve a preset chip to a concrete ``(from, to)`` date range. The
        FY start uses the frozen FY helper so the year is never hardcoded."""
        from app.contracts.flow import current_fy  # frozen FY helper (no reimpl)

        today = today or date.today()
        if preset is DatePreset.this_fy:
            fy_start_year = int(current_fy(today).split("-")[0])
            return date(fy_start_year, 4, 1), today
        if preset is DatePreset.this_month:
            return date(today.year, today.month, 1), today
        if preset is DatePreset.last_3_months:
            return _subtract_months(today, 3), today
        raise ValueError("custom range comes from the calendar, not a preset")

    def build_request(
        self,
        params: ExtractedParams,
        *,
        client_id: str,
        session_id: str,
        delivery: Delivery,
    ) -> PnlPdfRequest:
        """Build the ``GetGlobalPNLPDF`` request from collected params + the
        session identity. ``ClientId``/``UserId`` are the session-gated client
        code (identity trap: never user-supplied, ``UserId == ClientId``);
        ``Group`` is the mapped value; ``RequestFor`` is per delivery branch;
        ``With_Exp`` is the boolean ``True`` this endpoint expects."""
        if params.segment is None:
            raise ValueError("segment is required before generation")
        if not (params.date_range and params.date_range.from_ and params.date_range.to):
            raise ValueError("a resolved from/to date range is required before generation")
        return PnlPdfRequest(
            ClientId=client_id,
            UserId=client_id,  # identity trap: UserId == ClientId (client code)
            Group=SEGMENT_GROUP[params.segment],
            FromDate=params.date_range.from_.isoformat(),
            ToDate=params.date_range.to.isoformat(),
            RequestFor=REQUEST_FOR[delivery],
            With_Exp=True,  # boolean on the PDF endpoint (data API uses int 1)
            SessionId=session_id,
        )

    # -- date-window guardrail --------------------------------------------
    def clamp_end(self, start: date) -> date:
        """The dynamic 2-year clamp: the latest selectable end for a given start
        (exact across leap boundaries — the spec states the clamp in years)."""
        return _add_years(start, MAX_RANGE_YEARS)

    def build_calendar(self, *, today: date | None = None) -> Calendar:
        """The in-chat calendar bounds. Out-of-range dates are hard-disabled by
        the engine from ``min_date``/``max_date``; the 2-year clamp is applied
        dynamically once a start is picked (``clamp_end``)."""
        today = today or date.today()
        return Calendar(
            min_date=FLOOR,
            max_date=today + timedelta(days=CAP_RELATIVE_DAYS),
            max_range_days=None,  # dynamic clamp is by calendar year, not a day count
        )

    def validate_range(
        self, from_: date, to: date, *, today: date | None = None
    ) -> str | None:
        """Defensive validation for the FREE-TEXT range path (the calendar
        hard-disables invalid dates, so UI selections never reach here). Returns
        the flow's nudge copy on violation, else ``None``."""
        today = today or date.today()
        cap = today + timedelta(days=CAP_RELATIVE_DAYS)
        if from_ < FLOOR or to < FLOOR:
            return NUDGE_FLOOR
        if from_ > cap or to > cap:
            return NUDGE_CAP
        if to > self.clamp_end(from_):
            return NUDGE_RANGE
        return None

    # -- step render blocks (customer-facing copy) ------------------------
    def segment_step(self) -> ChipRow:
        return ChipRow(
            chips=[
                _chip("Equity", ChipActionKind.select_param, segment=Segment.equity.value),
                _chip("F&O", ChipActionKind.select_param, segment=Segment.fno.value),
                _chip("Commodity", ChipActionKind.select_param, segment=Segment.commodity.value),
            ]
        )

    def date_range_step(self) -> ChipRow:
        return ChipRow(
            chips=[
                _chip("This FY", ChipActionKind.select_param, preset=DatePreset.this_fy.value),
                _chip("This Month", ChipActionKind.select_param, preset=DatePreset.this_month.value),
                _chip("Last 3 months", ChipActionKind.select_param, preset=DatePreset.last_3_months.value),
                _chip("Custom range 📅", ChipActionKind.open_calendar),
            ]
        )

    def delivery_step(self) -> ChipRow:
        return ChipRow(
            chips=[
                _chip("📄 PDF, right here", ChipActionKind.select_param, delivery=Delivery.in_chat.value),
                _chip("✉️ Send to email", ChipActionKind.select_param, delivery=Delivery.email.value),
            ]
        )

    # -- generation / delivery render blocks ------------------------------
    def ack_bubble(self, segment: Segment) -> Bubble:
        return Bubble(text=f"On it — your {SEGMENT_LABEL[segment]} P&L…")

    def generating(self) -> Generating:
        return Generating(message="Generating your P&L…")

    def range_label(self, params: ExtractedParams) -> str:
        rng = params.date_range
        if not (rng and rng.from_ and rng.to):
            return "the selected period"
        fy = _fy_short_for_range(rng.from_, rng.to)
        span = f"{_fmt(rng.from_)} – {_fmt(rng.to)}"
        return f"{fy.replace('FY', 'FY ', 1)} · {span}" if fy else span

    def display_filename(self, params: ExtractedParams) -> str:
        """Renamed display filename ``PnL_<Segment>_<range>.pdf``. Deliberately
        carries NO Client ID and NO server path (the server name leaks the Client
        ID) — a security requirement, not a cosmetic one."""
        seg = SEGMENT_FILE_TOKEN[params.segment] if params.segment else "Report"
        rng = params.date_range
        if rng and rng.from_ and rng.to:
            token = _fy_short_for_range(rng.from_, rng.to) or f"{rng.from_:%Y%m%d}-{rng.to:%Y%m%d}"
        else:
            token = "range"
        return f"PnL_{seg}_{token}.pdf"

    def delivery_caption(self, params: ExtractedParams, *, today: date | None = None) -> Bubble:
        today = today or date.today()
        seg = SEGMENT_LABEL[params.segment] if params.segment else "P&L"
        return Bubble(
            text=(
                f"Your {seg} P&L for {self.range_label(params)} "
                f"(as of {_fmt(today)}, incl. charges)."
            )
        )

    def file_card(self, params: ExtractedParams, *, size_label: str) -> FileCard:
        """The delivered file card. Carries ONLY display-safe fields — no URL,
        no ``file_id``, no server filename. ``password_hint`` states the PAN
        password; the helper line is the frozen wire default."""
        return FileCard(
            filename=self.display_filename(params),
            size_label=size_label,
            format="pdf",
            password_hint=PASSWORD_HINT,
            actions=[_chip("✉️ Email it", ChipActionKind.email)],
        )

    def email_confirmation(self, response: str | None, params: ExtractedParams) -> Bubble:
        """Email-branch confirmation with the masked registered address."""
        seg = SEGMENT_LABEL[params.segment] if params.segment else "P&L"
        masked = mask_registered_email(response)
        return Bubble(
            text=(
                f"Done — your {seg} P&L for {self.range_label(params)} is on its way to "
                f"{masked}. Usually arrives within 2 minutes. Didn't get it? Tell me."
            )
        )

    def post_delivery_chips(self, delivery: Delivery) -> ChipRow:
        """Post-delivery affordances. The scrip-wise / Global-Detail hand-off is
        DEFERRED (no captured ``GetDetailedPNL`` file endpoint — proposal [GAP])."""
        if delivery is Delivery.email:
            return ChipRow(
                chips=[
                    _chip("↺ Resend", ChipActionKind.retry),
                    _chip("📄 Get it here", ChipActionKind.select_param, delivery=Delivery.in_chat.value),
                    _chip("🎫 Raise a ticket", ChipActionKind.raise_ticket),
                ]
            )
        return ChipRow(
            chips=[
                _chip("✉️ Email it", ChipActionKind.email),
                _chip("🎫 Raise a ticket", ChipActionKind.raise_ticket),
            ]
        )

    # -- delivery classification + error mapping --------------------------
    def delivery_kind(self, env: ParsedEnvelope) -> str:
        """Classify a successful polymorphic ``Response``: ``"download"`` (URL,
        fetched server-side) vs ``"email"`` (confirmation string). Reuses the
        frozen ``FileDeliveryResponse`` helpers."""
        payload = env.payload if isinstance(env.payload, str) else None
        resp = FileDeliveryResponse(Status="Success", Response=payload)
        if resp.is_email_confirmation():
            return "email"
        if resp.is_download_url():
            return "download"
        return "unknown"

    def is_session_expiry(self, env: ParsedEnvelope) -> bool:
        """HTTP-401 auth failure → session-expiry handling (a re-login path, NOT
        one of the five E-* taxonomy bubbles). The raw ``Reason`` (e.g.
        ``Invalid SessionId``) is never surfaced."""
        return env.outcome is Outcome.auth_error

    def error_code_for_envelope(self, env: ParsedEnvelope) -> ErrorCode | None:
        """In-band business outcome → taxonomy code. ``no_data`` → ``E-NODATA``;
        any other non-success (that is not the 401 session path) → ``E-UNKNOWN``.
        ``E-TIMEOUT`` / ``E-FETCH`` are raised from the engine's byte-fetch +
        one-silent-retry policy, not from an in-band envelope."""
        if env.outcome is Outcome.no_data:
            return ErrorCode.E_NODATA
        if env.outcome is Outcome.error:
            return ErrorCode.E_UNKNOWN
        return None  # success or auth (handled by is_session_expiry)

    def render_error(
        self,
        code: ErrorCode,
        *,
        fy_short: str | None = None,
        default_fy_short: str | None = None,
    ) -> ErrorBubble:
        """Render an ``error_bubble`` from the FROZEN ``error-taxonomy`` copy
        (emitted verbatim — the flow never redefines it). For ``E-FETCH`` the
        bubble carries the second line (shown only after the silent retry also
        fails); see ``fetch_retry_notice`` for the first line."""
        spec = ERROR_COPY[code]
        subs = {
            "FY_short": fy_short or "that period",
            "defaultFY": default_fy_short or "an in-window year",
        }
        text = spec.second_line if (code is ErrorCode.E_FETCH and spec.second_line) else spec.text
        return ErrorBubble(
            code=code,
            text=_safe_format(text, subs),
            chips=[_recovery_chip(_safe_format(label, subs)) for label in spec.chips],
        )

    def fetch_retry_notice(self) -> Bubble:
        """The first ``E-FETCH`` line, shown while the engine silently retries
        once (no recovery chips yet)."""
        return Bubble(text=ERROR_COPY[ErrorCode.E_FETCH].text)


#: The module-level attribute the engine's importlib discovery reads (D6). No
#: registration import, no decorator — presence of ``FLOW`` is the registration.
FLOW: PnlFlow = PnlFlow()
