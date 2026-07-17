"""Tax / Capital-Gain report flow (flow-tax-report capability).

The deterministic Tax Report state machine: an optional education line (Capital
Gain / Tax-P&L intents), dynamic 3-financial-year selection with AY→FY
confirmation and out-of-window E-YEAR guarding, the ``GetTaxReportPDF`` call in
PDF or Excel (or a both-formats email), a server-side byte-validated file card,
and the E-* error taxonomy.

Self-registration (D6): the module exposes a module-level ``FLOW`` object that
satisfies the frozen ``FlowSpec`` protocol; the engine's importlib discovery
registry (owned by flow-engine-runtime) auto-loads it by module presence. No
registration import is added anywhere, and this module never touches
``app/flows/__init__.py``.

The engine executor/cache is a parallel change whose runtime interface is not in
the frozen contracts, so the flow is a self-contained driver: it builds render
blocks and issues ``GetTaxReportPDF`` calls through the frozen ``FinXClient``
facade and a server-side byte-fetch callable, both injected via ``TaxFlowDeps``.

Security (03 §7): the ``GetTaxReportPDF`` ``Response`` URL and the server file
name are sensitive/unauthenticated — fetched server-side, never placed on a
render block or logged. The registered email in the email-branch confirmation is
masked before display. Only display-safe fields reach the wire.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Awaitable, Callable, Sequence

from app.contracts.errors import EC12, ERROR_COPY, ErrorCode
from app.contracts.flow import (
    ByteValidation,
    CacheConfig,
    DateWindow,
    FlowConfig,
    Step,
    StepKind,
    current_fy,
    default_fy,
    fy_long_to_short,
    supported_fys,
)
from app.contracts.router import (
    EDUCATION_LINE_INTENTS,
    TAX_FLOW_INTENTS,
    Intent,
    ReportFormat,
)
from app.contracts.wire import (
    Bubble,
    Chip,
    ChipAction,
    ChipActionKind,
    ChipRow,
    ErrorBubble,
    FileCard,
)
from app.finx.envelopes import Outcome, ParsedEnvelope
from app.finx.interfaces import FinXClient
from app.finx.models import TaxReportRequest

# ---------------------------------------------------------------------------
# Verbatim copy (flow spec §4). Placeholders in {braces} are runtime values.
# ---------------------------------------------------------------------------

#: S0 education lines — conditional, one bubble, before the stepper (§4.1).
EDUCATION_COPY: dict[Intent, str] = {
    Intent.report_capital_gain: (
        "Quick note — your capital gains are part of the Tax Report, so that's "
        "what I'll get you. It has everything you need for filing. 👍"
    ),
    Intent.report_tax_pnl: (
        "Heads-up — on FinX the Tax P&L is the Tax Report. Same document, one "
        "report. Setting it up now."
    ),
}

#: S1 · Financial year (§4.2).
FY_PROMPT = "Sure — which financial year?"
FY_HINT = "Current + last 2 financial years available."
FY_YTD_SUFFIX = " · year-to-date"  # sub-caption on the current (in-progress) FY chip.

#: S2 · Format & delivery (§4.3).
DELIVERY_PROMPT = "How do you want it?"
DELIVERY_PDF_LABEL = "📄 PDF, right here"
DELIVERY_EXCEL_LABEL = "📊 Excel, right here"
DELIVERY_EMAIL_LABEL = "✉️ Email me both"
DELIVERY_EMAIL_HINT = "PDF + Excel to your registered email."

#: EC-9 refusal (no registered email / send-elsewhere requested).
NO_EMAIL_REFUSAL = (
    "There's no email registered on your account yet — add one in Profile → "
    "Contact details, or get the file right here."
)

#: S4b · Email-sent card (§4.7).
EMAIL_SENT_SUBLINE = "Usually arrives within 2 minutes."
EMAIL_SENT_HELPER = "Didn't get it? Tell me."


# ---------------------------------------------------------------------------
# Financial-year resolution
# ---------------------------------------------------------------------------

_AY_RE = re.compile(r"\bA\.?\s*Y\.?\b|\bassessment\s+year\b", re.IGNORECASE)
_YEAR_PAIR_RE = re.compile(r"(20\d{2})\s*[-/–]\s*(\d{2,4})")
_SINGLE_YEAR_RE = re.compile(r"\b(20\d{2})\b")


class FyResolutionKind(str, Enum):
    """The outcome of interpreting a financial-year utterance."""

    confirmed = "confirmed"  # in-window FY, ready to proceed to S2
    needs_confirm = "needs_confirm"  # free-text FY in window → pre-filled confirm
    needs_ay_confirm = "needs_ay_confirm"  # AY mention → explicit AY→FY confirm
    out_of_window = "out_of_window"  # E-YEAR, no API call
    unparsed = "unparsed"  # no FY found → re-prompt with the chips


@dataclass
class FyResolution:
    kind: FyResolutionKind
    fy_long: str | None  # the resolved FY in "YYYY-YYYY" long form, when known
    blocks: list  # render blocks to emit for this resolution


def _parse_fy(text: str) -> tuple[bool, str | None]:
    """Parse a financial/assessment year from free text.

    Returns ``(is_ay, fy_long)`` where ``fy_long`` is the FINANCIAL year in long
    ``"YYYY-YYYY"`` form. An assessment year ``AY start-…`` maps to financial year
    ``start-1`` (AY 2026-27 → FY 2025-26)."""
    is_ay = bool(_AY_RE.search(text))
    pair = _YEAR_PAIR_RE.search(text)
    if pair:
        start = int(pair.group(1))
    else:
        single = _SINGLE_YEAR_RE.search(text)
        if not single:
            return is_ay, None
        start = int(single.group(1))
    if is_ay:
        start -= 1  # AY → FY
    return is_ay, f"{start}-{start + 1}"


# ---------------------------------------------------------------------------
# Injected runtime dependencies (kept out of the frozen contract surface)
# ---------------------------------------------------------------------------


@dataclass
class TaxFlowDeps:
    """Runtime dependencies the flow needs but that live outside the frozen
    contracts: the FinX facade and a server-side byte-fetch for the report URL.

    ``fetch_bytes`` fetches the (sensitive, server-side-only) report URL and
    returns its bytes; it raises ``TimeoutError`` on a network timeout and returns
    empty/short bytes for a 404 / empty body (both surface as E-FETCH after the
    one silent retry)."""

    finx: FinXClient
    fetch_bytes: Callable[[str], Awaitable[bytes]]
    today: date | None = None

    def now(self) -> date:
        return self.today or date.today()


# ---------------------------------------------------------------------------
# The flow
# ---------------------------------------------------------------------------


class TaxFlow:
    """Tax / Capital-Gain flow. Satisfies the frozen ``FlowSpec`` (``intent`` keys
    discovery, ``config`` carries the fy-based window, ``steps()`` yields the two
    stepper steps) and drives the deterministic walk via explicit methods."""

    #: Discovery key. Capital-Gain and Tax-P&L collapse onto this flow via the
    #: frozen ``TAX_FLOW_INTENTS`` set (see ``handles``).
    intent: Intent = Intent.report_tax
    #: The three intents this single flow fulfils (there is no separate CG API).
    intents = TAX_FLOW_INTENTS
    config: FlowConfig = FlowConfig(
        intent=Intent.report_tax, window=DateWindow(fy_based=True)
    )
    byte_validation: ByteValidation = ByteValidation()
    cache: CacheConfig = CacheConfig()

    # --- discovery (FlowSpec) -------------------------------------------------

    def steps(self) -> Sequence[Step]:
        """The two stepper steps: financial year, then format & delivery."""
        return (
            Step(id="fy", kind=StepKind.fy),
            Step(id="delivery", kind=StepKind.delivery),
        )

    @classmethod
    def handles(cls, intent: Intent) -> bool:
        """Whether this flow fulfils ``intent`` (tax / capital-gain / tax-P&L)."""
        return intent in TAX_FLOW_INTENTS

    # --- S0 · education -------------------------------------------------------

    def education_line(self, intent: Intent) -> Bubble | None:
        """The conditional S0 education bubble (Capital-Gain / Tax-P&L only)."""
        if intent not in EDUCATION_LINE_INTENTS:
            return None
        return Bubble(text=EDUCATION_COPY[intent])

    # --- S1 · financial year --------------------------------------------------

    def _fy_chip(self, fy_long: str, *, ytd: bool) -> Chip:
        label = fy_long_to_short(fy_long)
        if ytd:
            label += FY_YTD_SUFFIX
        return Chip(
            label=label,
            action=ChipAction(
                kind=ChipActionKind.select_param, payload={"fy": fy_long}
            ),
        )

    def fy_chips(self, today: date | None = None) -> list[Chip]:
        """The three FY chips: default (last completed FY) first and pre-highlighted,
        then the current (year-to-date) FY, then current-2. Computed dynamically."""
        cur = current_fy(today)
        dflt = default_fy(today)
        window = supported_fys(today)  # [current, current-1, current-2]
        oldest = window[2]
        return [
            self._fy_chip(dflt, ytd=False),  # default, first
            self._fy_chip(cur, ytd=True),  # current, year-to-date
            self._fy_chip(oldest, ytd=False),
        ]

    def fy_step_blocks(self, today: date | None = None) -> list:
        """S1 render: prompt, the three FY chips, and the hint line."""
        return [
            Bubble(text=FY_PROMPT),
            ChipRow(chips=self.fy_chips(today)),
            Bubble(text=FY_HINT),
        ]

    def resolve_fy(self, text: str, today: date | None = None) -> FyResolution:
        """Interpret a free-text financial-year utterance (EC-1 / EC-2).

        In-window plain FY → pre-filled confirm; AY mention → explicit AY→FY
        confirm; out-of-window → E-YEAR with the three FY chips and NO API call."""
        is_ay, fy_long = _parse_fy(text)
        if fy_long is None:
            return FyResolution(
                FyResolutionKind.unparsed, None, self.fy_step_blocks(today)
            )
        if fy_long not in supported_fys(today):
            return FyResolution(
                FyResolutionKind.out_of_window,
                fy_long,
                [self.error_bubble(ErrorCode.E_YEAR, fy_long, today)],
            )
        fy_short = fy_long_to_short(fy_long)
        if is_ay:
            ay_short = fy_long_to_short(f"{int(fy_long.split('-')[0]) + 1}-"
                                       f"{int(fy_long.split('-')[0]) + 2}")
            text_out = f"{ay_short.replace('FY', 'AY')} → that's {fy_short}, correct?"
            return FyResolution(
                FyResolutionKind.needs_ay_confirm,
                fy_long,
                [
                    Bubble(text=text_out),
                    ChipRow(
                        chips=[
                            self._confirm_chip(fy_long),
                            Chip(
                                label="Change year",
                                action=ChipAction(kind=ChipActionKind.send_text),
                            ),
                        ]
                    ),
                ],
            )
        text_out = f"Got it — Tax Report for {fy_short}. Confirm?"
        return FyResolution(
            FyResolutionKind.needs_confirm,
            fy_long,
            [
                Bubble(text=text_out),
                ChipRow(
                    chips=[
                        self._confirm_chip(fy_long),
                        Chip(
                            label="Change year",
                            action=ChipAction(kind=ChipActionKind.send_text),
                        ),
                    ]
                ),
            ],
        )

    def _confirm_chip(self, fy_long: str) -> Chip:
        return Chip(
            label="Confirm",
            action=ChipAction(
                kind=ChipActionKind.select_param, payload={"fy": fy_long}
            ),
        )

    # --- S2 · format & delivery ----------------------------------------------

    def delivery_step_blocks(self, *, hide_email: bool = False) -> list:
        """S2 render: the format/delivery chips. When ``hide_email`` (EC-9), only
        the two in-chat chips are offered."""
        chips = [
            Chip(
                label=DELIVERY_PDF_LABEL,
                action=ChipAction(
                    kind=ChipActionKind.select_param,
                    payload={"format": ReportFormat.pdf.value, "delivery": "in_chat"},
                ),
            ),
            Chip(
                label=DELIVERY_EXCEL_LABEL,
                action=ChipAction(
                    kind=ChipActionKind.select_param,
                    payload={"format": ReportFormat.excel.value, "delivery": "in_chat"},
                ),
            ),
        ]
        blocks: list = [Bubble(text=DELIVERY_PROMPT)]
        if not hide_email:
            chips.append(
                Chip(
                    label=DELIVERY_EMAIL_LABEL,
                    action=ChipAction(
                        kind=ChipActionKind.email, payload={"delivery": "email"}
                    ),
                )
            )
        blocks.append(ChipRow(chips=chips))
        if not hide_email:
            blocks.append(Bubble(text=DELIVERY_EMAIL_HINT))
        return blocks

    # --- S3/S4 · generate + deliver ------------------------------------------

    def _tax_request(
        self, *, client_id: str, fy_long: str, session_id: str, request_for: int,
        file_format: int,
    ) -> TaxReportRequest:
        return TaxReportRequest(
            ClientId=client_id,
            FinYear=fy_long,
            RequestFor=request_for,
            FileFormat=file_format,
            SessionId=session_id,
        )

    def _valid_bytes(self, data: bytes, fmt: ReportFormat) -> bool:
        if len(data) < self.byte_validation.min_bytes:
            return False
        magic = (
            self.byte_validation.pdf_magic
            if fmt is ReportFormat.pdf
            else self.byte_validation.excel_magic
        )
        return data.startswith(magic)

    async def deliver_here(
        self,
        *,
        fy_long: str,
        intent: Intent,
        client_id: str,
        session_id: str,
        fmt: ReportFormat,
        deps: TaxFlowDeps,
    ) -> list:
        """In-chat delivery (RequestFor 2). Calls ``GetTaxReportPDF``, fetches the
        report URL server-side, byte-validates it, and — on a validation failure —
        performs exactly one silent auto-retry (fresh generation) before surfacing
        E-FETCH. Returns the file-card blocks or an error bubble."""
        req = self._tax_request(
            client_id=client_id,
            fy_long=fy_long,
            session_id=session_id,
            request_for=2,  # ViewType-compliant download (tax only)
            file_format=1 if fmt is ReportFormat.pdf else 2,
        )
        attempts = self.byte_validation.silent_retries + 1
        for _ in range(attempts):
            try:
                env = await deps.finx.dotnet.get_tax_report_pdf(req)
            except TimeoutError:
                return [self.error_bubble(ErrorCode.E_TIMEOUT, fy_long, deps.today)]
            terminal = self._terminal_error(env, fy_long, deps.today)
            if terminal is not None:
                return [terminal]
            try:
                data = await deps.fetch_bytes(str(env.payload))
            except TimeoutError:
                return [self.error_bubble(ErrorCode.E_TIMEOUT, fy_long, deps.today)]
            if self._valid_bytes(data, fmt):
                return self.file_card_blocks(
                    fy_long=fy_long, intent=intent, fmt=fmt, data=data, today=deps.today
                )
            # invalid bytes → silently retry a fresh generation
        return [self.error_bubble(ErrorCode.E_FETCH, fy_long, deps.today)]

    async def deliver_email(
        self,
        *,
        fy_long: str,
        client_id: str,
        session_id: str,
        deps: TaxFlowDeps,
    ) -> list:
        """Email delivery (RequestFor 1): two calls, FileFormat 1 then 2. Middleware
        sends the mail; the flow never handles the address, and masks the registered
        email from the confirmation before display. EC-12 on partial failure."""
        results: dict[str, tuple[str, str | None]] = {}
        for key, file_format in (("pdf", 1), ("xlsx", 2)):
            req = self._tax_request(
                client_id=client_id,
                fy_long=fy_long,
                session_id=session_id,
                request_for=1,  # email
                file_format=file_format,
            )
            try:
                env = await deps.finx.dotnet.get_tax_report_pdf(req)
            except TimeoutError:
                results[key] = ("timeout", None)
                continue
            if env.outcome is Outcome.success:
                results[key] = ("ok", str(env.payload) if env.payload else None)
            elif env.outcome is Outcome.no_data:
                results[key] = ("no_data", None)
            else:
                results[key] = ("error", None)

        pdf_ok = results["pdf"][0] == "ok"
        xlsx_ok = results["xlsx"][0] == "ok"
        fy_short = fy_long_to_short(fy_long)

        if pdf_ok and xlsx_ok:
            masked = self._masked_from(results["pdf"][1], results["xlsx"][1])
            return [
                Bubble(
                    text=(
                        f"Done — your Tax Report for {fy_short} (PDF + Excel) is on "
                        f"its way to {masked}."
                    )
                ),
                Bubble(text=EMAIL_SENT_SUBLINE),
                Bubble(text=EMAIL_SENT_HELPER),
                self._email_recovery_chips(),
            ]
        if pdf_ok and not xlsx_ok:
            masked = self._masked_from(results["pdf"][1])
            return [
                ErrorBubble(
                    code=ErrorCode.E_FETCH,
                    text=EC12.text.format(masked_email=masked),
                    chips=[self._chip_for_label(lbl, fy_long) for lbl in EC12.chips],
                )
            ]
        # PDF leg itself failed → map from its outcome.
        code = {
            "timeout": ErrorCode.E_TIMEOUT,
            "no_data": ErrorCode.E_NODATA,
        }.get(results["pdf"][0], ErrorCode.E_UNKNOWN)
        return [self.error_bubble(code, fy_long, deps.today)]

    def _masked_from(self, *confirmations: str | None) -> str:
        for conf in confirmations:
            if not conf:
                continue
            email = _extract_email(conf)
            if email:
                return mask_email(email)
        return "your registered email"

    # --- delivery render blocks ----------------------------------------------

    def file_card_blocks(
        self,
        *,
        fy_long: str,
        intent: Intent,
        fmt: ReportFormat,
        data: bytes,
        today: date | None = None,
    ) -> list:
        """Lead-in bubble + file card (renamed, no password) + post-delivery chips.
        The current-FY provisional caption is added when FY is the in-progress year."""
        fy_short = fy_long_to_short(fy_long)
        ext = "pdf" if fmt is ReportFormat.pdf else "xlsx"
        lead_in = f"Here's your Tax Report for {fy_short}"
        if intent is Intent.report_capital_gain:
            lead_in += " — capital gains are inside"
        blocks: list = [Bubble(text=lead_in)]
        if fy_long == current_fy(today):
            start_year = fy_long.split("-")[0]
            now = today or date.today()
            blocks.append(
                Bubble(
                    text=(
                        f"Covers 1 Apr {start_year} – {now.day} "
                        f"{now.strftime('%b')} {now.year} · year-to-date, figures "
                        f"may change till 31 Mar."
                    )
                )
            )
        blocks.append(
            FileCard(
                filename=f"Tax_Report_{fy_short.replace(' ', '')}.{ext}",
                size_label=_size_label(len(data)),
                format=ext,  # "pdf" | "xlsx"
                password_hint=None,  # tax files are not password-protected
                actions=self._post_delivery_chips(fy_long, fmt),
            )
        )
        return blocks

    def _post_delivery_chips(self, fy_long: str, delivered: ReportFormat) -> list[Chip]:
        other = ReportFormat.excel if delivered is ReportFormat.pdf else ReportFormat.pdf
        other_label = "📊 Also get it as Excel" if other is ReportFormat.excel else "📄 Also get it as PDF"
        return [
            Chip(
                label=other_label,
                action=ChipAction(
                    kind=ChipActionKind.select_param,
                    payload={"format": other.value, "delivery": "in_chat", "fy": fy_long},
                ),
            ),
            Chip(
                label=DELIVERY_EMAIL_LABEL,
                action=ChipAction(kind=ChipActionKind.email, payload={"fy": fy_long}),
            ),
            Chip(
                label="🎫 Raise a ticket",
                action=ChipAction(kind=ChipActionKind.raise_ticket),
            ),
        ]

    def _email_recovery_chips(self) -> ChipRow:
        return ChipRow(
            chips=[
                Chip(label="↺ Resend", action=ChipAction(kind=ChipActionKind.retry)),
                Chip(
                    label="📄 Get it here instead",
                    action=ChipAction(
                        kind=ChipActionKind.select_param,
                        payload={"format": ReportFormat.pdf.value, "delivery": "in_chat"},
                    ),
                ),
                Chip(
                    label="🎫 Raise a ticket",
                    action=ChipAction(kind=ChipActionKind.raise_ticket),
                ),
            ]
        )

    # --- errors ---------------------------------------------------------------

    def _terminal_error(
        self, env: ParsedEnvelope, fy_long: str, today: date | None
    ) -> ErrorBubble | None:
        """Map a non-success envelope to its error bubble; ``None`` on success.
        no_data → E-NODATA; anything else (error / auth) → E-UNKNOWN. (Session/EC-7
        is engine-owned and has no code in the frozen 5-code taxonomy.)"""
        if env.outcome is Outcome.success:
            return None
        if env.outcome is Outcome.no_data:
            return self.error_bubble(ErrorCode.E_NODATA, fy_long, today)
        return self.error_bubble(ErrorCode.E_UNKNOWN, fy_long, today)

    def error_bubble(
        self, code: ErrorCode, fy_long: str | None, today: date | None = None
    ) -> ErrorBubble:
        """Build an ErrorBubble from the frozen ERROR_COPY. Copy never exposes a
        Reason, HTTP code, or URL; only the bracketed placeholders are substituted."""
        spec = ERROR_COPY[code]
        fy_short = fy_long_to_short(fy_long) if fy_long else ""
        default_short = fy_long_to_short(default_fy(today))
        window_short = [fy_long_to_short(fy) for fy in supported_fys(today)]
        list_str = _humanize_list(window_short)
        text = _fmt(spec.text, FY_short=fy_short, defaultFY=default_short, list=list_str)
        if spec.second_line:  # E-FETCH: both lines surface after the failed retry
            text = f"{text} {spec.second_line}"
        if spec.dynamic_chips == "fy_window":
            chips = self.fy_chips(today)
        else:
            chips = [
                self._chip_for_label(
                    _fmt(lbl, FY_short=fy_short, defaultFY=default_short, list=list_str),
                    default_fy(today),
                )
                for lbl in spec.chips
            ]
        return ErrorBubble(code=code, text=text, chips=chips)

    def _chip_for_label(self, label: str, fy_long: str) -> Chip:
        """Map a verbatim recovery-chip label to a typed chip action."""
        low = label.lower()
        if "ticket" in low:
            return Chip(label=label, action=ChipAction(kind=ChipActionKind.raise_ticket))
        if "email" in low:
            return Chip(label=label, action=ChipAction(kind=ChipActionKind.email))
        if "try fy" in low or "in-window" in low:
            return Chip(
                label=label,
                action=ChipAction(
                    kind=ChipActionKind.select_param, payload={"fy": fy_long}
                ),
            )
        if "get excel here" in low or "get it here" in low:
            fmt = ReportFormat.excel if "excel" in low else ReportFormat.pdf
            return Chip(
                label=label,
                action=ChipAction(
                    kind=ChipActionKind.select_param,
                    payload={"format": fmt.value, "delivery": "in_chat"},
                ),
            )
        return Chip(label=label, action=ChipAction(kind=ChipActionKind.retry))


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _extract_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text)
    return match.group(0) if match else None


def mask_email(addr: str) -> str:
    """Mask a registered email like the P&L flow (``sandeep.harsha@gmail.com`` →
    ``san***.harsha@gmail.com``): keep the first three local characters and the
    local part from its last dot; the domain is shown in full."""
    addr = addr.strip().lower()
    if "@" not in addr:
        return addr
    local, domain = addr.split("@", 1)
    if "." in local:
        idx = local.rindex(".")
        return f"{local[:3]}***{local[idx:]}@{domain}"
    return f"{local[:3]}***@{domain}"


def _size_label(num_bytes: int) -> str:
    kb = max(1, round(num_bytes / 1024))
    if kb < 1024:
        return f"{kb} KB"
    return f"{kb / 1024:.1f} MB"


def _humanize_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _fmt(template: str, **kwargs: object) -> str:
    """``str.format`` restricted to the known error-copy placeholders. Missing
    placeholders in ``template`` simply are not substituted; extras are ignored."""
    return template.format(**kwargs)


# ---------------------------------------------------------------------------
# Module-level registration object (D6): the engine's importlib discovery reads it.
# ---------------------------------------------------------------------------

FLOW: TaxFlow = TaxFlow()
