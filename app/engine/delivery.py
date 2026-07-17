"""Delivery assembly (proposal §Byte-validation…, §Per-flow 15-min cache, §Delivery).

At the generation step the engine invokes the flow's adapter binding, fetches the
report bytes through the injected byte-fetch primitive, applies exactly ONE silent
retry on ``FinXFetchError`` (fresh generation → fresh URL → refetch) before the
E-FETCH bubble, maps ``FinXTimeoutError`` → E-TIMEOUT and in-band results →
E-NODATA/E-UNKNOWN, serves/stores the 15-minute selection cache (``resend``
bypasses), and builds the file-card (renamed display filename, CML excepted;
password hint; helper) or the masked email-confirmation / EC-12 blocks.

The engine imports NO HTTP or magic-byte logic — that primitive is the injected
``ByteFetcher``. It owns only the retry/error policy and the presentation around it.
"""

from __future__ import annotations

from typing import Literal

from app.contracts.errors import EC12
from app.contracts.flow import selection_cache_key
from app.contracts.router import ExtractedParams, Intent, ReportFormat
from app.contracts.wire import Bubble, ChipRow, ErrorBubble, FileCard, RenderBlock

from app.engine.chips import chip_for_label
from app.engine.errors import map_error
from app.engine.faults import FinXFetchError, FinXTimeoutError
from app.engine.ports import (
    EmailResult,
    EngineContext,
    FlowDefinition,
    GenerationError,
    NoData,
    ReportBytes,
    ReportUrl,
)

#: Engine-default email-confirmation copy (no frozen taxonomy entry). [CONFIRM]
EMAIL_CONFIRMATION = "On its way to {masked_email} — check your inbox in a minute."


def _wire_format(fmt: ReportFormat) -> Literal["pdf", "xlsx"]:
    return "xlsx" if fmt is ReportFormat.excel else "pdf"


def _size_label(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    kb = n / 1024
    if kb < 1024:
        return f"{round(kb)} KB"
    return f"{kb / 1024:.1f} MB"


def _filename(flow: FlowDefinition, params: ExtractedParams, fmt: ReportFormat) -> str:
    # CML keeps the server's own name; every other flow is renamed so the display
    # filename never leaks the Client ID (02 §2.6).
    if flow.intent is Intent.report_cml:
        return "Client_Master_List.pdf"
    return f"{flow.report_title(params)}.{_wire_format(fmt)}"


def _resolve_format(params: ExtractedParams, flow: FlowDefinition, result=None) -> ReportFormat:
    if result is not None and getattr(result, "report_format", None) is not None:
        return result.report_format
    return params.report_format or flow.default_format


def mask_email(raw: str) -> str:
    """Mask a FinX-leaked registered email before display: keep the first three
    local-part chars, ``***``, then from the first ``.`` onward, plus the domain.
    ``SANJAY.HARSHA@GMAIL.COM`` → ``san***.harsha@gmail.com``; ``sanjayharsha@…`` →
    ``san***@…``."""
    s = raw.strip().lower()
    local, _, domain = s.partition("@")
    dot = local.find(".")
    masked_local = local[:3] + "***" + (local[dot:] if dot >= 3 else "")
    return masked_local + (f"@{domain}" if domain else "")


def _file_card(flow: FlowDefinition, params: ExtractedParams, fmt: ReportFormat, data: bytes) -> FileCard:
    actions = [chip_for_label("✉️ Email it to me")] if flow.supports_email else []
    return FileCard(
        filename=_filename(flow, params, fmt),
        size_label=_size_label(len(data)),
        format=_wire_format(fmt),
        password_hint=flow.password_hint,
        actions=actions,
    )


def _email_blocks(
    flow: FlowDefinition, params: ExtractedParams, ctx: EngineContext, result: EmailResult
) -> list[RenderBlock]:
    masked = mask_email(result.raw_email)
    if result.failed and result.sent:
        # EC-12 partial dual-format email failure.
        return [
            Bubble(text=EC12.text.replace("{masked_email}", masked)),
            ChipRow(chips=[chip_for_label(lbl) for lbl in EC12.chips]),
        ]
    if not result.sent:
        return [map_error(GenerationError(), flow, ctx=ctx, params=params)]
    return [Bubble(text=EMAIL_CONFIRMATION.replace("{masked_email}", masked))]


async def _fetch_with_retry(
    flow: FlowDefinition, params: ExtractedParams, ctx: EngineContext, result: ReportUrl
) -> bytes | ErrorBubble:
    """Fetch the report bytes with EXACTLY one silent retry on FinXFetchError."""
    try:
        return await ctx.byte_fetcher(result.url, expected_format=result.report_format)
    except FinXTimeoutError as exc:
        return map_error(exc, flow, ctx=ctx, params=params)
    except FinXFetchError:
        pass  # fall through to the single silent retry

    retry = await flow.generate(params, ctx)  # fresh generation → fresh URL
    if isinstance(retry, ReportBytes):
        return retry.data
    if not isinstance(retry, ReportUrl):
        # Retry produced an in-band result rather than a URL — map it directly.
        return map_error(retry, flow, ctx=ctx, params=params)
    try:
        return await ctx.byte_fetcher(retry.url, expected_format=retry.report_format)
    except (FinXFetchError, FinXTimeoutError) as exc:
        return map_error(exc, flow, ctx=ctx, params=params)


async def deliver(
    flow: FlowDefinition,
    params: ExtractedParams,
    ctx: EngineContext,
    *,
    resend: bool = False,
) -> list[RenderBlock]:
    """Generate + deliver. Returns the ordered render blocks (a file card, an
    email-confirmation / EC-12, or an error bubble)."""
    key = selection_cache_key(flow.intent, params)

    if not resend:
        cached = ctx.cache.get(key, now=ctx.now)
        if cached is not None:
            fmt = _resolve_format(params, flow)
            return [_file_card(flow, params, fmt, cached)]

    result = await flow.generate(params, ctx)

    if isinstance(result, (NoData, GenerationError)):
        return [map_error(result, flow, ctx=ctx, params=params)]
    if isinstance(result, EmailResult):
        return _email_blocks(flow, params, ctx, result)
    if isinstance(result, ReportBytes):
        ctx.cache.put(key, result.data, now=ctx.now)
        return [_file_card(flow, params, result.report_format, result.data)]
    if isinstance(result, ReportUrl):
        outcome = await _fetch_with_retry(flow, params, ctx, result)
        if isinstance(outcome, ErrorBubble):
            return [outcome]
        ctx.cache.put(key, outcome, now=ctx.now)
        return [_file_card(flow, params, result.report_format, outcome)]

    # Defensive: an unknown result shape maps to E-UNKNOWN.
    return [map_error(GenerationError(), flow, ctx=ctx, params=params)]
