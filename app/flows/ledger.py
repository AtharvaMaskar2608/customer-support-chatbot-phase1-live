"""Ledger / MTF-Ledger flow module (flow-ledger-mtf capability).

One deterministic spine, two report types (Ledger = ``Margin:0``, MTF Ledger =
``Margin:1`` [CONFIRM]): report-type -> date-range -> delivery, then a server-side
``GetLedgerDetailsPDF`` call and a byte-validated PDF file card (or a masked-email
confirmation).

Self-registration: this module exposes the module-level ``FLOW`` object that the
engine's importlib discovery reads (``app.contracts.flow.FLOW_ATTR``). It imports
no register function and edits no shared registry — ``app/flows/__init__.py`` is
engine-owned and untouched (``app/flows/`` is a namespace package here).

Builds against frozen contracts only. The ``FinXClient`` facade and the
server-side PDF fetch are injected, so the flow is exercised entirely against
fixture-based fakes with no live API.

Security invariant (03 §7): the report URL, the server filename, and the
registered email are sensitive. The URL is fetched server-side and discarded; it
is never placed in a render block and never logged. The email confirmation leaks
the full (uppercased) address and is masked before display.
"""

from __future__ import annotations

import asyncio
import calendar as _calendar
from collections.abc import Awaitable, Callable, Sequence
from datetime import date, timedelta
from enum import Enum

from app.contracts.errors import ERROR_COPY, ErrorCode
from app.contracts.flow import (
    ByteValidation,
    DateWindow,
    FlowConfig,
    Step,
    StepKind,
    StepState,
    default_fy,
)
from app.contracts.router import Delivery, Intent
from app.contracts.wire import (
    Bubble,
    Calendar,
    Chip,
    ChipAction,
    ChipActionKind,
    ChipRow,
    ErrorBubble,
    FileCard,
    RenderBlock,
)
from app.finx.envelopes import Outcome, ParsedEnvelope
from app.finx.interfaces import FinXClient
from app.finx.models import LedgerPdfRequest

# ---------------------------------------------------------------------------
# Report type <-> Margin discriminator
# ---------------------------------------------------------------------------


class ReportType(str, Enum):
    """The two report types this flow serves, driven by the report-type step."""

    ledger = "ledger"
    mtf = "mtf"


#: ``Margin`` discriminator on GetLedgerDetailsPDF. 0 = normal ledger (confirmed);
#: 1 = MTF [CONFIRM — unproven] (``Margin:0``/``:1`` were byte-identical on the
#: no-MTF test account, so MTF fidelity is unverified until an MTF-holding capture).
MARGIN: dict[ReportType, int] = {ReportType.ledger: 0, ReportType.mtf: 1}

#: Friendly-filename prefix (no client code ever appears in the filename).
FILENAME_PREFIX: dict[ReportType, str] = {
    ReportType.ledger: "Ledger",
    ReportType.mtf: "MTF_Ledger",
}

#: Customer-safe label used in captions and step summaries.
REPORT_LABEL: dict[ReportType, str] = {
    ReportType.ledger: "Ledger",
    ReportType.mtf: "MTF Ledger",
}


def report_type_for_intent(intent: Intent) -> ReportType | None:
    """The report type an entry intent pre-selects, or ``None`` when the intent is
    ambiguous (``report_ledger`` alone from the Reports screen still shows both
    chips only when the router did not name the type — here the ledger intent
    pre-selects Ledger, the MTF intent pre-selects MTF)."""
    if intent is Intent.report_mtf_ledger:
        return ReportType.mtf
    if intent is Intent.report_ledger:
        return ReportType.ledger
    return None


# ---------------------------------------------------------------------------
# Per-flow date window (floor 2019-01-01, cap today+7, NO max-range clamp)
# ---------------------------------------------------------------------------

#: Calendar floor: dates before 1 Jan 2019 are hard-disabled (spec §2 / flow §2.5).
LEDGER_FLOOR: date = date(2019, 1, 1)
#: Cap = today + 7 days [CONFIRM]. No max-range clamp — a 2019->today range is valid.
CAP_RELATIVE_DAYS: int = 7

#: The earliest-range chip offered on the out-of-window nudge (Jan 2019 – Dec 2020).
EARLIEST_RANGE: tuple[date, date] = (date(2019, 1, 1), date(2020, 12, 31))


def window_bounds(today: date | None = None) -> tuple[date, date]:
    """The ``(floor, cap)`` selectable bounds for a given day."""
    today = today or date.today()
    return LEDGER_FLOOR, today + timedelta(days=CAP_RELATIVE_DAYS)


def in_window(day: date, today: date | None = None) -> bool:
    floor, cap = window_bounds(today)
    return floor <= day <= cap


def range_in_window(from_date: date, to_date: date, today: date | None = None) -> bool:
    """A range is valid when both ends sit within ``[floor, cap]`` and are ordered.
    There is NO maximum-span clamp (EC-6): a full 2019->today range is valid."""
    floor, cap = window_bounds(today)
    return floor <= from_date <= to_date <= cap


def _months_ago(day: date, months: int) -> date:
    month = day.month - months
    year = day.year
    while month <= 0:
        month += 12
        year -= 1
    last = _calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def last_3_months_range(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return _months_ago(today, 3), today


def last_fy_range(today: date | None = None) -> tuple[date, date]:
    """The last completed financial year (1 Apr -> 31 Mar), computed from the
    shared FY helper so the Apr-1 rollover lives in exactly one place."""
    today = today or date.today()
    start = int(default_fy(today).split("-")[0])
    return date(start, 4, 1), date(start + 1, 3, 31)


# ---------------------------------------------------------------------------
# Display formatting (filenames, captions, prose ranges, sizes)
# ---------------------------------------------------------------------------


def _fmt_file_date(day: date) -> str:
    """``1Apr2025`` — day (no leading zero), 3-letter month, 4-digit year."""
    return f"{day.day}{day.strftime('%b')}{day.year}"


def _fmt_caption_date(day: date) -> str:
    """``1 Apr 2025`` — the spaced caption form."""
    return f"{day.day} {day.strftime('%b')} {day.year}"


def caption_range(from_date: date, to_date: date) -> str:
    """``1 Apr 2025 – 31 Mar 2026`` (en dash, spaced)."""
    return f"{_fmt_caption_date(from_date)} – {_fmt_caption_date(to_date)}"


def display_filename(report_type: ReportType, from_date: date, to_date: date) -> str:
    """``Ledger_1Apr2025-31Mar2026.pdf`` / ``MTF_Ledger_...`` — friendly rename,
    never the server filename (which leaks the client code)."""
    return (
        f"{FILENAME_PREFIX[report_type]}_"
        f"{_fmt_file_date(from_date)}-{_fmt_file_date(to_date)}.pdf"
    )


def caption(report_type: ReportType, from_date: date, to_date: date) -> str:
    return f"Here's your {REPORT_LABEL[report_type]} for {caption_range(from_date, to_date)}"


def _prose_range(from_date: date, to_date: date) -> tuple[str, str]:
    """``("14 Apr", "14 Jul 2026")`` — the year is dropped from the start label
    when both ends share a year (matches the EC-1 sample copy)."""
    to_label = f"{to_date.day} {to_date.strftime('%b')} {to_date.year}"
    if from_date.year == to_date.year:
        from_label = f"{from_date.day} {from_date.strftime('%b')}"
    else:
        from_label = f"{from_date.day} {from_date.strftime('%b')} {from_date.year}"
    return from_label, to_label


def _size_label(n_bytes: int) -> str:
    return f"{max(1, round(n_bytes / 1024))} KB"


# ---------------------------------------------------------------------------
# Email masking (the FinX confirmation leaks the full uppercased address)
# ---------------------------------------------------------------------------


def mask_email(raw: str) -> str:
    """Mask a registered email for display: keep the first three local-part
    characters and any segment after the first dot, lowercased (the confirmation
    arrives uppercased). ``SANJAY.HARSHA@GMAIL.COM`` -> ``san***.harsha@gmail.com``."""
    local, sep, domain = raw.partition("@")
    local = local.strip().lower()
    domain = domain.strip().lower()
    if not sep or not local or not domain:
        return "your registered email"
    if "." in local:
        head, _, tail = local.partition(".")
        masked_local = f"{head[:3]}***.{tail}"
    else:
        masked_local = f"{local[:3]}***"
    return f"{masked_local}@{domain}"


def _extract_email(confirmation: str) -> str | None:
    """Pull the address out of a ``"... mail sent successfully to X@Y"`` string."""
    for token in reversed(confirmation.split()):
        if "@" in token:
            return token.strip().rstrip(".")
    return None


# ---------------------------------------------------------------------------
# Request builder
# ---------------------------------------------------------------------------


def build_ledger_request(
    *,
    client_code: str,
    session_id: str,
    report_type: ReportType,
    from_date: date,
    to_date: date,
    delivery: Delivery,
) -> LedgerPdfRequest:
    """Build the GetLedgerDetailsPDF request exactly as captured (03 §4.2).

    ``LoginId`` is the CLIENT CODE (not the data API's ``"JIFFY"`` literal);
    ``Group`` is ``"GROUP1"`` UPPERCASE (the data API uses ``"Group1"``);
    ``Margin`` is 0/1 per report type [CONFIRM for MTF]; ``RequestFor`` is 0 for a
    download and 1 for email [CONFIRM — email branch untested]."""
    return LedgerPdfRequest(
        ClientId=client_code,
        LoginId=client_code,  # client code, NOT "JIFFY"
        Group="GROUP1",  # uppercase [CONFIRM casing]
        Margin=MARGIN[report_type],  # 1 = MTF [CONFIRM]
        FromDate=from_date.isoformat(),
        ToDate=to_date.isoformat(),
        RequestFor=1 if delivery is Delivery.email else 0,  # email=1 [CONFIRM]
        SessionId=session_id,
    )


# ---------------------------------------------------------------------------
# Chip / block builders
# ---------------------------------------------------------------------------


def _chip(label: str, kind: ChipActionKind, payload: dict[str, str] | None = None) -> Chip:
    return Chip(label=label, action=ChipAction(kind=kind, payload=payload or {}))


_RAISE_TICKET_CHIP = _chip("\U0001f3ab Raise a ticket", ChipActionKind.raise_ticket)
_TRY_DIFFERENT_RANGE_CHIP = _chip("Try a different range", ChipActionKind.open_calendar)


def report_type_chips() -> ChipRow:
    """Step 1 chips: Ledger / MTF Ledger (both labels are customer-safe)."""
    return ChipRow(
        chips=[
            _chip("Ledger", ChipActionKind.select_param, {"report_type": ReportType.ledger.value}),
            _chip("MTF Ledger", ChipActionKind.select_param, {"report_type": ReportType.mtf.value}),
        ]
    )


def date_preset_chips(today: date | None = None) -> ChipRow:
    """Step 2 preset chips with RESOLVED dates (V2 style) so "Last FY" is
    unambiguous. Custom opens the calendar."""
    today = today or date.today()
    l3_from, l3_to = last_3_months_range(today)
    fy_from, fy_to = last_fy_range(today)
    return ChipRow(
        chips=[
            _chip(
                "Last 3 months",
                ChipActionKind.select_param,
                {"from": l3_from.isoformat(), "to": l3_to.isoformat()},
            ),
            _chip(
                f"Last FY · {caption_range(fy_from, fy_to)}",
                ChipActionKind.select_param,
                {"from": fy_from.isoformat(), "to": fy_to.isoformat()},
            ),
            _chip("Custom range \U0001f4c5", ChipActionKind.open_calendar),
        ]
    )


def delivery_chips() -> ChipRow:
    """Step 3 chips: PDF here / email. No Excel for ledger."""
    return ChipRow(
        chips=[
            _chip("\U0001f4c4 PDF, right here", ChipActionKind.select_param, {"delivery": Delivery.in_chat.value}),
            _chip("✉️ Send to email", ChipActionKind.select_param, {"delivery": Delivery.email.value}),
        ]
    )


def build_calendar(today: date | None = None) -> Calendar:
    """The Custom-range calendar: floor 2019-01-01, cap today+7, no clamp. The
    engine hard-disables out-of-range dates rather than validating after."""
    floor, cap = window_bounds(today)
    return Calendar(min_date=floor, max_date=cap, disabled_ranges=[], max_range_days=None)


#: Verbatim out-of-window nudge copy (flow §2.5).
OUT_OF_WINDOW_TEXT: str = (
    "I can pull ledger entries from Jan 2019 onwards — records before that "
    "aren't available here. Want the earliest possible instead?"
)


def out_of_window_response(today: date | None = None) -> list[RenderBlock]:
    """Free-text out-of-window request ("ledger for 2017"): a conversational
    nudge + earliest-range chip. No API call is made."""
    earliest_from, earliest_to = EARLIEST_RANGE
    return [
        Bubble(text=OUT_OF_WINDOW_TEXT),
        ChipRow(
            chips=[
                _chip(
                    "Jan 2019 – Dec 2020",
                    ChipActionKind.select_param,
                    {"from": earliest_from.isoformat(), "to": earliest_to.isoformat()},
                ),
                _chip("\U0001f4c5 Pick dates", ChipActionKind.open_calendar),
            ]
        ),
    ]


def future_clamp_confirm(today: date | None = None) -> list[RenderBlock]:
    """EC-4: an end date beyond today+7 typed in free text -> clamp with confirm."""
    _, cap = window_bounds(today)
    return [
        Bubble(text=f"I can include up to {_fmt_caption_date(cap)} — set that as the end date?"),
        ChipRow(
            chips=[
                _chip("Yes, use that", ChipActionKind.select_param, {"to": cap.isoformat()}),
                _chip("\U0001f4c5 Pick dates", ChipActionKind.open_calendar),
            ]
        ),
    ]


# ---------------------------------------------------------------------------
# Error / failure blocks
# ---------------------------------------------------------------------------


def nodata_ledger(from_date: date, to_date: date) -> ErrorBubble:
    """EC-1: empty range for a normal Ledger -> E-NODATA with ledger-specific copy."""
    from_label, to_label = _prose_range(from_date, to_date)
    return ErrorBubble(
        code=ErrorCode.E_NODATA,
        text=f"No ledger entries found between {from_label} and {to_label}, so there's nothing to report there.",
        chips=[_TRY_DIFFERENT_RANGE_CHIP, _RAISE_TICKET_CHIP],
    )


def nodata_mtf() -> ErrorBubble:
    """EC-2: no MTF activity -> plain no-data copy (no MTF education)."""
    return ErrorBubble(
        code=ErrorCode.E_NODATA,
        text="No data available for MTF Ledger in that range.",
        chips=[
            _chip("Try Ledger instead", ChipActionKind.select_param, {"report_type": ReportType.ledger.value}),
            _TRY_DIFFERENT_RANGE_CHIP,
        ],
    )


def fetch_failed() -> ErrorBubble:
    """EC-5: the file generated but the bytes never arrived cleanly (after the one
    silent retry) -> E-FETCH with ledger-specific copy. Never mentions the API."""
    return ErrorBubble(
        code=ErrorCode.E_FETCH,
        text="The ledger generated but didn't come through cleanly on my side.",
        chips=[
            _chip("↺ Try again", ChipActionKind.retry, {"bypass_cache": "true"}),
            _chip("✉️ Email it instead", ChipActionKind.email),
            _RAISE_TICKET_CHIP,
        ],
    )


def timeout_error() -> ErrorBubble:
    """E-TIMEOUT — the generic frozen copy (selections are saved)."""
    return ErrorBubble(
        code=ErrorCode.E_TIMEOUT,
        text=ERROR_COPY[ErrorCode.E_TIMEOUT].text,
        chips=[_chip("↺ Retry", ChipActionKind.retry), _RAISE_TICKET_CHIP],
    )


def unknown_error() -> ErrorBubble:
    """E-UNKNOWN — any other non-success Status."""
    return ErrorBubble(
        code=ErrorCode.E_UNKNOWN,
        text=ERROR_COPY[ErrorCode.E_UNKNOWN].text,
        chips=[_chip("↺ Retry", ChipActionKind.retry), _RAISE_TICKET_CHIP],
    )


#: EC-7 session-expiry copy (auth failure has no E-code; it is a Bubble + chips).
SESSION_EXPIRY_TEXT: str = "Your session timed out… your selections are saved."


def session_expiry() -> list[RenderBlock]:
    return [
        Bubble(text=SESSION_EXPIRY_TEXT),
        ChipRow(chips=[_chip("Log in again", ChipActionKind.deep_link, {"target": "login"})]),
    ]


# ---------------------------------------------------------------------------
# Delivery driver (server-side fetch + byte validation + one silent retry)
# ---------------------------------------------------------------------------

#: Fetches the report bytes from the (server-side-only) report URL. Injected so the
#: flow is testable without network; the URL is never logged or surfaced.
PdfFetcher = Callable[[str], Awaitable[bytes]]


def _valid_pdf(data: bytes, validation: ByteValidation) -> bool:
    return len(data) >= validation.min_bytes and data.startswith(validation.pdf_magic)


def _terminal_error(
    env: ParsedEnvelope,
    report_type: ReportType,
    from_date: date,
    to_date: date,
) -> list[RenderBlock] | None:
    """Map a non-success envelope to its terminal blocks, or ``None`` on success.
    The raw ``env.reason`` is never surfaced (it is logged server-side only)."""
    if env.outcome is Outcome.success:
        return None
    if env.outcome is Outcome.no_data:
        if report_type is ReportType.mtf:
            return [nodata_mtf()]
        return [nodata_ledger(from_date, to_date)]
    if env.outcome is Outcome.auth_error:
        return session_expiry()
    return [unknown_error()]  # Outcome.error


def _download_delivery_blocks(
    report_type: ReportType, from_date: date, to_date: date, data: bytes
) -> list[RenderBlock]:
    return [
        Bubble(text=caption(report_type, from_date, to_date)),
        FileCard(
            filename=display_filename(report_type, from_date, to_date),
            size_label=_size_label(len(data)),
            format="pdf",
            password_hint=None,  # ledger PDFs are not password protected
            helper="Trouble opening it? Tell me.",
            actions=[
                _chip("↺ Send it again", ChipActionKind.retry, {"bypass_cache": "true"}),
                _chip("✉️ Email it instead", ChipActionKind.email),
                _RAISE_TICKET_CHIP,
            ],
        ),
    ]


async def _deliver_download(
    client: FinXClient,
    fetch: PdfFetcher,
    *,
    client_code: str,
    session_id: str,
    report_type: ReportType,
    from_date: date,
    to_date: date,
    validation: ByteValidation,
) -> list[RenderBlock]:
    req = build_ledger_request(
        client_code=client_code,
        session_id=session_id,
        report_type=report_type,
        from_date=from_date,
        to_date=to_date,
        delivery=Delivery.in_chat,
    )
    # Exactly one silent auto-retry on broken bytes -> at most two full generations.
    attempts = validation.silent_retries + 1
    for _ in range(attempts):
        try:
            env = await client.dotnet.get_ledger_details_pdf(req)
        except (TimeoutError, asyncio.TimeoutError):
            return [timeout_error()]
        terminal = _terminal_error(env, report_type, from_date, to_date)
        if terminal is not None:
            return terminal
        # Success -> payload is the report URL. Fetch server-side; never log/surface it.
        url = env.payload if isinstance(env.payload, str) else ""
        try:
            data = await fetch(url)
        except (TimeoutError, asyncio.TimeoutError):
            return [timeout_error()]
        except Exception:
            data = b""  # broken download -> retry, then E-FETCH
        if _valid_pdf(data, validation):
            return _download_delivery_blocks(report_type, from_date, to_date, data)
    return [fetch_failed()]


async def _deliver_email(
    client: FinXClient,
    *,
    client_code: str,
    session_id: str,
    report_type: ReportType,
    from_date: date,
    to_date: date,
) -> list[RenderBlock]:
    req = build_ledger_request(
        client_code=client_code,
        session_id=session_id,
        report_type=report_type,
        from_date=from_date,
        to_date=to_date,
        delivery=Delivery.email,
    )
    try:
        env = await client.dotnet.get_ledger_details_pdf(req)
    except (TimeoutError, asyncio.TimeoutError):
        return [timeout_error()]
    terminal = _terminal_error(env, report_type, from_date, to_date)
    if terminal is not None:
        return terminal
    confirmation = env.payload if isinstance(env.payload, str) else ""
    address = _extract_email(confirmation)
    masked = mask_email(address) if address else "your registered email"
    return [
        Bubble(
            text=(
                f"Done — your {REPORT_LABEL[report_type]} for "
                f"{caption_range(from_date, to_date)} is on its way to {masked}."
            )
        ),
        Bubble(text="Usually arrives within 2 minutes."),
        ChipRow(
            chips=[
                _chip("↺ Resend", ChipActionKind.retry, {"bypass_cache": "true"}),
                _chip("\U0001f4c4 Get it here as PDF", ChipActionKind.select_param, {"delivery": Delivery.in_chat.value}),
                _RAISE_TICKET_CHIP,
            ]
        ),
    ]


async def generate_and_deliver(
    client: FinXClient,
    fetch: PdfFetcher,
    *,
    client_code: str,
    session_id: str,
    report_type: ReportType,
    from_date: date,
    to_date: date,
    delivery: Delivery,
    validation: ByteValidation | None = None,
) -> list[RenderBlock]:
    """Drive Step 4: call GetLedgerDetailsPDF and deliver. Download does a
    server-side byte-validated fetch with one silent retry; email masks the
    registered address. All failures map to conversational bubbles."""
    validation = validation or ByteValidation()
    if delivery is Delivery.email:
        return await _deliver_email(
            client,
            client_code=client_code,
            session_id=session_id,
            report_type=report_type,
            from_date=from_date,
            to_date=to_date,
        )
    return await _deliver_download(
        client,
        fetch,
        client_code=client_code,
        session_id=session_id,
        report_type=report_type,
        from_date=from_date,
        to_date=to_date,
        validation=validation,
    )


# ---------------------------------------------------------------------------
# Flow definition + module-level FLOW registration (FlowSpec)
# ---------------------------------------------------------------------------


def _base_steps() -> list[Step]:
    return [
        # No dedicated report-type StepKind exists in the frozen enum; `segment` is
        # the generic categorical chip-row kind (test_flow.py: segment -> chip row).
        Step(id="report_type", kind=StepKind.segment),
        Step(id="date_range", kind=StepKind.date_range),
        Step(id="delivery", kind=StepKind.delivery),
        Step(id="generate", kind=StepKind.generate),
    ]


def initial_steps(intent: Intent) -> list[Step]:
    """The stepper's entry state. When the entry intent names the report type,
    Step 1 is shown pre-completed (and still editable) and Step 2 opens active;
    otherwise Step 1 opens active with both chips."""
    rt = report_type_for_intent(intent)
    steps = _base_steps()
    if rt is not None:
        steps[0].state = StepState.done
        steps[0].selected_label = REPORT_LABEL[rt]
        steps[1].state = StepState.active
    else:
        steps[0].state = StepState.active
    return steps


class LedgerFlow:
    """The Ledger / MTF-Ledger flow. Satisfies the frozen ``FlowSpec`` protocol.

    ``intent`` (the FlowSpec-required, discovery key) is ``report_ledger``; the MTF
    report type is the same flow with the report-type step pre-set to MTF. The
    additive ``intents`` tuple lets a multi-intent discovery also key
    ``report_mtf_ledger`` to this flow (integration note: depends on the engine's
    discovery honoring it — flagged in loop.md)."""

    intent: Intent = Intent.report_ledger
    intents: tuple[Intent, ...] = (Intent.report_ledger, Intent.report_mtf_ledger)
    config: FlowConfig = FlowConfig(
        intent=Intent.report_ledger,
        window=DateWindow(
            floor=LEDGER_FLOOR,
            cap_relative_days=CAP_RELATIVE_DAYS,
            max_range_years=None,  # NO max-range clamp
        ),
    )

    def steps(self) -> Sequence[Step]:
        return _base_steps()


#: The module-level attribute the engine's importlib discovery reads.
FLOW: LedgerFlow = LedgerFlow()
