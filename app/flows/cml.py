"""CML report flow (flow-cml capability).

The simplest, zero-user-input report flow: on ``Intent.report_cml`` the flow makes
a single ``POST /mis/reports/generate`` call over the SSO-JWT / MIS adapter (never
the SessionId), reads ``body.cmlLink``, fetches the file bytes **server-side**,
byte-validates them, and delivers a file card that keeps the server's own filename
``Client_Master_List.pdf``.

Registration is by discovery: this module exposes a module-level ``FLOW`` object
satisfying the frozen ``FlowSpec`` (``app/contracts/flow.py``); the engine's
importlib registry auto-loads it by module presence — this module imports no
registration function and never edits ``app/flows/__init__.py``.

Security (03 §7 FLAG B): the signed ``cmlLink`` is NOT a security boundary — its
``X-Amz-Expires`` / single-use is defeated by CloudFront path caching — so it is
fetched immediately and then discarded. It is never cached, never logged, and
never placed in any render block (the frozen ``FileCard`` carries no URL field).

Division of labor: the flow reuses the frozen shared semantics — ``ByteValidation``
/ ``PDF_MAGIC`` for validation and ``ERROR_COPY`` / ``ErrorCode`` for error copy —
rather than redefining them; it emits error *codes* and renders their verbatim
copy + recovery chips from the frozen ``error-taxonomy``.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Sequence

from pydantic import ValidationError

from app.contracts.errors import ERROR_COPY, ErrorCode
from app.contracts.flow import (
    ByteValidation,
    DateWindow,
    FlowConfig,
    Step,
    StepKind,
    StepState,
)
from app.contracts.router import Intent
from app.contracts.wire import (
    Chip,
    ChipAction,
    ChipActionKind,
    ChipRow,
    ErrorBubble,
    FileCard,
    RenderBlock,
    SessionContext,
)
from app.finx.envelopes import Outcome, ParsedEnvelope
from app.finx.interfaces import FinXClient
from app.finx.models import CmlBody, CmlRequest

#: An injected, server-side byte fetcher for the signed ``cmlLink``. The real
#: implementation is the adapters' ``fetch_report_bytes`` primitive (change 1);
#: tests inject a fake. The URL passed here is fetched and discarded — never
#: retained by the flow.
ByteFetcher = Callable[[str], Awaitable[bytes]]

# ---------------------------------------------------------------------------
# Flow-specific declarations
# ---------------------------------------------------------------------------

#: §2.6 carve-out — CML keeps the server's own filename (it leaks no Client ID).
DISPLAY_FILENAME: str = "Client_Master_List.pdf"
FILE_FORMAT: str = "pdf"
#: [ASSUMPTION] the CML PDF is unprotected (spec §9 item 12) — no password line.
PASSWORD_HINT: str | None = None
#: Latency copy the engine emits as a ``generating`` block if the turn exceeds ~5s.
GENERATING_MESSAGE: str = "Getting your CML…"

#: Frozen byte-validation config: size floor + ``%PDF`` magic + exactly one silent
#: auto-retry (a fresh API call — the prior link is dead).
_VALIDATION: ByteValidation = ByteValidation()


# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------


def _send_again_chip() -> Chip:
    """Re-runs the flow with a fresh API call — the old signed link is dead, so
    ``resend`` bypasses any byte cache and re-generates."""
    return Chip(
        label="↺ Send it again",
        action=ChipAction(kind=ChipActionKind.retry, payload={"resend": "true"}),
    )


def post_delivery_chips() -> list[Chip]:
    """[↺ Send it again · Something incorrect in it? 🎫 Raise a ticket]. A CML
    correction is an address/bank/nominee service request — a ticket, not a
    re-download."""
    return [
        _send_again_chip(),
        Chip(
            label="Something incorrect in it? 🎫 Raise a ticket",
            action=ChipAction(kind=ChipActionKind.raise_ticket),
        ),
    ]


def recovery_chips() -> list[Chip]:
    """Failure recovery chips [↺ Send it again · 🎫 Raise a ticket] (proposal
    render-sequence #4). CML has no email / dual-format path, so the frozen
    taxonomy's default E-FETCH "Email me both" chip does not apply — this flow
    supplies its own recovery chips. The error TEXT is still the frozen verbatim
    copy (see ``_error_block``); only the recovery-chip set is flow-specific."""
    return [
        _send_again_chip(),
        Chip(label="🎫 Raise a ticket", action=ChipAction(kind=ChipActionKind.raise_ticket)),
    ]


def _error_block(code: ErrorCode) -> ErrorBubble:
    """Emit the code with the frozen verbatim error TEXT (never redefined) and the
    CML-specific recovery chips."""
    return ErrorBubble(code=code, text=ERROR_COPY[code].text, chips=recovery_chips())


# ---------------------------------------------------------------------------
# Generation path
# ---------------------------------------------------------------------------


def _build_request(ctx: SessionContext) -> CmlRequest:
    """``{reportType:"cml", searchBy:"client-id", searchValue:<session client>}``.
    ``searchValue`` is the authenticated session's Client ID (``ctx.user_id``) —
    never the SessionId, never user-supplied. The frozen ``CmlRequest`` has no
    SessionId field, so it is structurally impossible to send one here."""
    return CmlRequest(searchValue=ctx.user_id)


def _extract_link(env: ParsedEnvelope) -> str | None:
    """``body.cmlLink`` from a success envelope, or ``None`` if missing/empty."""
    payload = env.payload
    if not isinstance(payload, dict):
        return None
    try:
        body = CmlBody.model_validate(payload)
    except ValidationError:
        return None
    link = body.cmlLink.strip()
    return link or None


def _valid_pdf(data: bytes) -> bool:
    return len(data) >= _VALIDATION.min_bytes and data.startswith(_VALIDATION.pdf_magic)


def _human_size(n: int) -> str:
    kb = n / 1024
    if kb < 1024:
        return f"{round(kb)} KB"
    return f"{kb / 1024:.1f} MB"


def _delivery_blocks(size_bytes: int) -> list[RenderBlock]:
    card = FileCard(
        filename=DISPLAY_FILENAME,
        size_label=_human_size(size_bytes),
        format=FILE_FORMAT,
        password_hint=PASSWORD_HINT,
        # helper keeps the frozen default "Trouble opening it? Tell me."
    )
    return [card, ChipRow(chips=post_delivery_chips())]


async def _generate_and_deliver(
    client: FinXClient, ctx: SessionContext, fetch_bytes: ByteFetcher
) -> list[RenderBlock]:
    """One CML generation: API → link → server-side fetch → validate → file card.
    On invalid bytes, retry exactly once with a fresh API call (the old link is
    dead); a second failure surfaces ``E-FETCH``."""
    attempts = _VALIDATION.silent_retries + 1  # one silent retry → two attempts
    for _ in range(attempts):
        env = await client.mis.generate_report(_build_request(ctx))
        if env.outcome is not Outcome.success:
            # auth-401 / non-200 / any other non-success — CML has no no-data case.
            return [_error_block(ErrorCode.E_UNKNOWN)]
        link = _extract_link(env)
        if link is None:
            return [_error_block(ErrorCode.E_UNKNOWN)]  # missing/empty cmlLink
        data = await fetch_bytes(link)  # server-side; the link is discarded here
        if _valid_pdf(data):
            return _delivery_blocks(len(data))
    return [_error_block(ErrorCode.E_FETCH)]


async def run(
    client: FinXClient,
    ctx: SessionContext,
    fetch_bytes: ByteFetcher,
    *,
    resend: bool = False,
) -> list[RenderBlock]:
    """Drive the whole zero-step CML flow and return the ordered render blocks.

    ``resend`` is accepted for engine-interface symmetry; the flow caches no link
    or bytes, so every call already re-generates from a fresh API call. A timeout
    anywhere (API or byte fetch) maps to ``E-TIMEOUT`` with selections preserved.
    """
    try:
        return await _generate_and_deliver(client, ctx, fetch_bytes)
    except TimeoutError:
        return [_error_block(ErrorCode.E_TIMEOUT)]


# ---------------------------------------------------------------------------
# Discovery handle
# ---------------------------------------------------------------------------


class CmlFlow:
    """The module-level flow object the engine discovers. Satisfies the frozen
    ``FlowSpec`` (``intent`` / ``config`` / ``steps()``) and carries the CML
    declarations + generation entry point the engine binds at the generate step."""

    intent: Intent = Intent.report_cml
    config: FlowConfig = FlowConfig(intent=Intent.report_cml, window=DateWindow())

    # Declarations the engine's delivery assembly reads.
    display_filename: str = DISPLAY_FILENAME
    file_format: str = FILE_FORMAT
    password_hint: str | None = PASSWORD_HINT
    generating_message: str = GENERATING_MESSAGE

    def steps(self) -> Sequence[Step]:
        # Zero user-input flow: a single terminal generate step (no collection).
        return [Step(id="generate", kind=StepKind.generate, state=StepState.active)]

    def post_delivery_chips(self) -> list[Chip]:
        return post_delivery_chips()

    def recovery_chips(self, code: ErrorCode) -> list[Chip]:
        # CML renders one flow-specific recovery set for every error code
        # (proposal render-seq #4): the frozen taxonomy's E-FETCH "Email me
        # both" chip has no CML email/dual-format path, so `code` does not vary
        # the chips. Error TEXT is still the frozen verbatim copy (see run()).
        return recovery_chips()

    async def run(
        self,
        client: FinXClient,
        ctx: SessionContext,
        fetch_bytes: ByteFetcher,
        *,
        resend: bool = False,
    ) -> list[RenderBlock]:
        return await run(client, ctx, fetch_bytes, resend=resend)


#: The attribute the engine's importlib discovery reads (``FLOW_ATTR``).
FLOW: CmlFlow = CmlFlow()
