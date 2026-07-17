"""Contract Note flow (flow-contract-notes capability).

The deterministic Phase-1 Contract Note flow: one date-range step → a per-trading-
day note list → per-note server-side download → in-chat file card, with bulk =
email-all only. Self-registers by exposing a module-level ``FLOW`` object that the
engine's importlib discovery reads (``FLOW_ATTR``) — no registration import, no
edit to ``app/flows/__init__.py``.

Two FinX endpoints back the flow (both consumed via the frozen ``FinXClient.go``
adapter, which owns the header/prefix auth):

* list — ``POST finx.choiceindia.com/middleware-go/report/contract`` (Go
  envelope; branch on the body ``StatusCode`` the parser already normalized);
* per-note download — ``POST api.choiceindia.com/middleware-go/contract/download``
  (raw PDF bytes back, not an envelope).

SECURITY — FLAG A (03 §7). Both endpoints enforced NO authentication in testing,
authorizing purely on the body ``client_id`` / ``client_code``. This flow is the
primary place FLAG A is defended:

* ``client_id`` / ``client_code`` are ALWAYS the authenticated session's
  ``user_id`` — the flow API has no parameter that accepts a user-supplied one;
* the FinX ``file_id`` is sensitive: it lives ONLY inside a session-scoped
  :class:`DownloadTokenVault`, is never placed on the wire (rows carry an opaque
  ``downloadToken`` instead), and is never logged.
"""

from __future__ import annotations

import secrets
from collections import Counter
from datetime import date, timedelta
from typing import Sequence

from app.config.defaults import DEFAULT_CONFIG
from app.config.schema import RemoteConfig
from app.contracts.errors import ERROR_COPY, ErrorCode
from app.contracts.flow import (
    ByteValidation,
    FlowConfig,
    Step,
    StepKind,
    StepState,
)
from app.contracts.router import Intent
from app.contracts.wire import (
    Bubble,
    Calendar,
    Chip,
    ChipAction,
    ChipActionKind,
    ChipRow,
    ErrorBubble,
    FileCard,
    NoteListCard,
    NoteRow,
    RenderBlock,
)
from app.finx.envelopes import Outcome
from app.finx.interfaces import FinXClient
from app.finx.models import (
    ContractNote,
    ContractNoteDownloadRequest,
    ContractNoteListBody,
    ContractNoteListRequest,
)

#: This flow's intent (frozen router enum). The proposal's ``Intent.CONTRACT_NOTES``
#: is shorthand for this value.
_CN_INTENT = Intent.report_contract_notes

#: Size + magic-byte validation applied before delivery, with exactly one silent
#: auto-retry (frozen defaults: min 1024 bytes, ``%PDF`` magic, silent_retries=1).
_BYTES = ByteValidation()

#: Customer-facing segment label per FinX group, matched case-insensitively. Only
#: ``Grp1`` (equity + F&O) and ``MCX`` (commodity) are known; the badge shows only
#: on dual-note days.
_GROUP_SEGMENT: dict[str, str] = {"GRP1": "Equity & F&O", "MCX": "Commodity"}
_COMMODITY_GROUP = "MCX"


# ---------------------------------------------------------------------------
# FLAG A: session-scoped file_id vault
# ---------------------------------------------------------------------------


class DownloadTokenVault:
    """Session-scoped opaque-token ↔ contract-note map (FLAG A defense).

    The FinX ``file_id`` MUST never reach the client or logs. The list step issues
    an opaque token per note and hands the client only the token; the note (with
    its ``file_id``) stays here, partitioned by ``session_id`` so a token from one
    widget session cannot resolve in another. The frozen ``FlowState`` has no slot
    for this map, so the vault is the server-side store.
    """

    def __init__(self) -> None:
        self._by_session: dict[str, dict[str, ContractNote]] = {}

    def issue(self, session_id: str, note: ContractNote) -> str:
        """Store ``note`` under a fresh opaque token scoped to ``session_id`` and
        return the token (the only handle the client ever sees)."""
        token = secrets.token_urlsafe(24)
        self._by_session.setdefault(session_id, {})[token] = note
        return token

    def resolve(self, session_id: str, token: str) -> ContractNote | None:
        """Return the note for ``token`` within ``session_id`` (or ``None`` for an
        unknown / cross-session / expired token)."""
        return self._by_session.get(session_id, {}).get(token)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _parse_trade_date(ddmmyyyy: str) -> date:
    """Parse the list row's ``DDMMYYYY`` trade date into a ``date``."""
    return date(int(ddmmyyyy[4:8]), int(ddmmyyyy[2:4]), int(ddmmyyyy[0:2]))


def _segment_label(group: str) -> str | None:
    return _GROUP_SEGMENT.get(group.strip().upper())


def _is_commodity(group: str) -> bool:
    return group.strip().upper() == _COMMODITY_GROUP


def _valid_pdf(data: bytes) -> bool:
    """Size-floor + ``%PDF`` magic-byte check (the CN PDFs are unprotected)."""
    return len(data) >= _BYTES.min_bytes and data.startswith(_BYTES.pdf_magic)


def _size_label(n_bytes: int) -> str:
    if n_bytes >= 1024 * 1024:
        return f"{n_bytes / (1024 * 1024):.1f} MB"
    return f"{max(1, round(n_bytes / 1024))} KB"


def _display_filename(note: ContractNote) -> str:
    """Renamed display filename — never the server ``CN_<ClientId>_...`` name,
    which leaks the Client ID. ``_MCX`` marks the commodity note."""
    name = f"Contract_Note_{_parse_trade_date(note.date).isoformat()}"
    if _is_commodity(note.group):
        name += "_MCX"
    return f"{name}.pdf"


def _last_trading_day(today: date) -> date:
    """Most recent weekday on/before ``today`` (exchange holidays are not modeled —
    the list API is the source of truth for whether a note exists)."""
    d = today
    while d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        d -= timedelta(days=1)
    return d


def _chip(label: str, kind: ChipActionKind, **payload: str) -> Chip:
    return Chip(label=label, action=ChipAction(kind=kind, payload=dict(payload)))


# ---------------------------------------------------------------------------
# The flow
# ---------------------------------------------------------------------------


class ContractNoteFlow:
    """The Contract Note state machine. Satisfies the frozen ``FlowSpec`` protocol
    (``intent`` / ``config`` / ``steps()``) for discovery, and owns the full CN
    logic against the frozen ``FinXClient`` protocol (a fake driver stands in for
    the parallel adapters in tests)."""

    def __init__(
        self,
        *,
        config: RemoteConfig = DEFAULT_CONFIG,
        vault: DownloadTokenVault | None = None,
    ) -> None:
        self.intent = _CN_INTENT
        self.config = FlowConfig(intent=_CN_INTENT, window=config.calendar_bounds[_CN_INTENT])
        self._limits = config.limits
        self._vault = vault or DownloadTokenVault()

    # -- FlowSpec ---------------------------------------------------------

    def steps(self) -> Sequence[Step]:
        """The flow's ordered steps: the user collects a date range; delivery is
        the fetch → note-list → per-note download the engine drives afterward."""
        return [
            Step(id="date-range", kind=StepKind.date_range, state=StepState.active),
            Step(id="delivery", kind=StepKind.delivery, state=StepState.pending),
        ]

    # -- Step 1: date range ----------------------------------------------

    def date_range_step(self, *, today: date | None = None) -> list[RenderBlock]:
        """The date-range chip row (presets with resolved dates + a custom-range
        chip that opens the calendar)."""
        today = today or date.today()
        ltd = _last_trading_day(today)
        return [
            ChipRow(
                chips=[
                    _chip("Last trading day", ChipActionKind.select_param, **{"from": ltd.isoformat(), "to": ltd.isoformat()}),
                    _chip("Last 7 days", ChipActionKind.select_param, **{"from": (today - timedelta(days=6)).isoformat(), "to": today.isoformat()}),
                    _chip("This month", ChipActionKind.select_param, **{"from": today.replace(day=1).isoformat(), "to": today.isoformat()}),
                    _chip("Custom range", ChipActionKind.open_calendar),
                ]
            )
        ]

    def calendar(self, *, today: date | None = None) -> Calendar:
        """The custom-range calendar: floor 2018-01-01, cap today (notes exist only
        for completed trading days — no +7), no max range."""
        today = today or date.today()
        window = self.config.window
        cap = today + timedelta(days=window.cap_relative_days or 0)
        return Calendar(min_date=window.floor, max_date=cap, max_range_days=None)

    # -- Step 2: fetch & branch ------------------------------------------

    async def fetch(
        self,
        session,
        *,
        from_date: str,
        to_date: str,
        finx: FinXClient,
    ) -> list[RenderBlock]:
        """Drive the list call and branch on the body ``StatusCode`` (as normalized
        by the frozen Go parser): 204 → no-data explainer · 1 note → direct
        delivery · 2+ → note-list · >threshold → narrow-nudge.

        SECURITY: ``client_id`` is the session ``user_id`` — never user input.
        """
        req = ContractNoteListRequest(
            client_id=session.user_id, from_date=from_date, to_date=to_date
        )
        try:
            env = await finx.go.list_contract_notes(req)
        except TimeoutError:
            return [self._error(ErrorCode.E_TIMEOUT)]
        except Exception:
            return [self._error(ErrorCode.E_UNKNOWN)]

        if env.outcome is Outcome.no_data:
            return [self._no_data()]
        if env.outcome is not Outcome.success:
            return [self._error(ErrorCode.E_UNKNOWN)]

        notes = list(ContractNoteListBody.model_validate(env.payload).contractNotes)
        if not notes:
            return [self._no_data()]
        if len(notes) == 1:
            # Exactly one note → skip the list, deliver directly (server-side).
            return await self._deliver_note(session, notes[0], finx)
        if len(notes) > self._limits.note_narrow_threshold:
            return self._narrow_nudge(len(notes))
        return self._note_list(session, notes)

    # -- Step 3: per-note delivery ---------------------------------------

    async def download(self, session, download_token: str, *, finx: FinXClient) -> list[RenderBlock]:
        """Deliver the note behind an opaque ``download_token`` (a row tap).

        SECURITY: the ``file_id`` comes only from the session-scoped vault — never
        from the client. An unknown / cross-session token yields E-FETCH.
        """
        note = self._vault.resolve(session.session_id, download_token)
        if note is None:
            return [self._error(ErrorCode.E_FETCH)]
        return await self._deliver_note(session, note, finx)

    async def _deliver_note(self, session, note: ContractNote, finx: FinXClient) -> list[RenderBlock]:
        """Download → validate → (one silent retry) → file card, else E-FETCH /
        E-TIMEOUT. ``client_code`` is the session ``user_id``; ``file_id`` stays
        server-side."""
        req = ContractNoteDownloadRequest(client_code=session.user_id, file_id=note.file_id)
        try:
            data = await self._download_once(finx, req)
            if data is None:
                data = await self._download_once(finx, req)  # exactly one silent retry
            if data is None:
                return [self._error(ErrorCode.E_FETCH)]
        except TimeoutError:
            return [self._error(ErrorCode.E_TIMEOUT)]
        return [self._file_card(note, len(data)), self._post_delivery_chips()]

    async def _download_once(self, finx: FinXClient, req: ContractNoteDownloadRequest) -> bytes | None:
        """One download attempt. Valid bytes → the bytes; a 404 / 0 bytes / wrong
        magic / transport error → ``None`` (a failed attempt). Timeout propagates
        so it maps to E-TIMEOUT, not the E-FETCH retry path."""
        try:
            data = await finx.go.download_contract_note(req)
        except TimeoutError:
            raise
        except Exception:
            return None
        return data if _valid_pdf(data) else None

    # -- Step 4: email branch --------------------------------------------

    def email_confirmation(self, *, masked_email: str, count: int | None = None) -> list[RenderBlock]:
        """The single / bulk email-all confirmation. The address is pre-masked by
        the orchestrator (no raw email or PII enters this flow); the CN endpoints
        have no email mode, so the actual send is orchestrator-owned."""
        if count and count > 1:
            text = f"On its way — all {count} contract notes are headed to {masked_email}."
        else:
            text = f"On its way — that contract note is headed to {masked_email}."
        return [
            Bubble(text=text),
            ChipRow(
                chips=[
                    _chip("📅 Change dates", ChipActionKind.open_calendar),
                    _chip("🎫 Raise a ticket", ChipActionKind.raise_ticket),
                ]
            ),
        ]

    # -- Render builders --------------------------------------------------

    def _note_list(self, session, notes: list[ContractNote]) -> list[RenderBlock]:
        """The note-list card: rows keyed by ``file_id`` (server-side) but carrying
        only the opaque ``downloadToken``, newest first, with month dividers and
        dual-note segment badges."""
        ordered = sorted(notes, key=lambda n: _parse_trade_date(n.date), reverse=True)
        per_date = Counter(n.date for n in notes)
        rows: list[NoteRow] = []
        dividers: list[str] = []
        for note in ordered:
            d = _parse_trade_date(note.date)
            month = d.strftime("%B %Y")
            if month not in dividers:
                dividers.append(month)
            dual = per_date[note.date] >= 2
            rows.append(
                NoteRow(
                    date_label=d.strftime("%d %b %Y"),
                    weekday=d.strftime("%A"),
                    download_token=self._vault.issue(session.session_id, note),
                    segment_badge=_segment_label(note.group) if dual else None,
                )
            )
        return [
            NoteListCard(
                rows=rows,
                page_size=self._limits.contract_note_page_size,
                total=len(notes),
                month_dividers=dividers,
                footer_chips=[
                    _chip(f"✉️ Email all {len(notes)}", ChipActionKind.email, scope="all"),
                    _chip("📅 Change dates", ChipActionKind.open_calendar),
                ],
            )
        ]

    def _narrow_nudge(self, count: int) -> list[RenderBlock]:
        """The >threshold nudge shown BEFORE the list — email-all or narrow."""
        return [
            Bubble(
                text=(
                    f"That range has {count} contract notes — more than I can lay out "
                    "cleanly here. Want them all by email, or shall we narrow the dates?"
                )
            ),
            ChipRow(
                chips=[
                    _chip(f"✉️ Email all {count}", ChipActionKind.email, scope="all"),
                    _chip("📅 Narrow the range", ChipActionKind.open_calendar),
                ]
            ),
        ]

    def _file_card(self, note: ContractNote, n_bytes: int) -> FileCard:
        return FileCard(
            filename=_display_filename(note),
            size_label=_size_label(n_bytes),
            format="pdf",
            password_hint=None,  # CN PDFs are unprotected
        )

    def _post_delivery_chips(self) -> ChipRow:
        return ChipRow(
            chips=[
                _chip("✉️ Email this note", ChipActionKind.email, scope="single"),
                _chip("📅 Other dates", ChipActionKind.open_calendar),
            ]
        )

    def _no_data(self) -> ErrorBubble:
        """204 → E-NODATA with the mandatory CN explainer (the taxonomy's default
        E-NODATA copy is tax-flavored, so the text is overridden here)."""
        return ErrorBubble(
            code=ErrorCode.E_NODATA,
            text=(
                "I couldn't find any contract notes for those dates. Contract notes "
                "are only generated for the days you actually traded — try a wider "
                "range or a different day."
            ),
            chips=[
                _chip("📅 Change dates", ChipActionKind.open_calendar),
                _chip("🎫 Raise a ticket", ChipActionKind.raise_ticket),
            ],
        )

    def _error(self, code: ErrorCode) -> ErrorBubble:
        return ErrorBubble(code=code, text=ERROR_COPY[code].text, chips=self._recovery_chips(code))

    def _recovery_chips(self, code: ErrorCode) -> list[Chip]:
        if code is ErrorCode.E_FETCH:
            return [
                _chip("↺ Try again", ChipActionKind.retry),
                _chip("✉️ Email this note", ChipActionKind.email, scope="single"),
                _chip("🎫 Raise a ticket", ChipActionKind.raise_ticket),
            ]
        return [
            _chip("↺ Retry", ChipActionKind.retry),
            _chip("🎫 Raise a ticket", ChipActionKind.raise_ticket),
        ]


#: The module-level attribute the engine's importlib discovery reads (``FLOW_ATTR``).
FLOW = ContractNoteFlow()
