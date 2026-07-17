"""The thin LLM router (llm-router capability).

A pure function over ``(utterance, ConversationContext)``: one forced native
``route`` tool call (the frozen ``ROUTE_TOOL_CHOICE``) whose ``tool_use.input``
materializes a ``RouterResult``, wrapped in deterministic post-processing —
§2.5 intent precedence, FY/AY normalization + confirmation, §8.5 sticky-language,
and one-shot follow-up / cap escalation. No FinX, no DB, no stepper control; the
router only classifies and extracts.

Every type consumed here is the frozen ``router-contract`` /
``flow-engine-contract`` / ``llm-client`` from ``contracts-foundation`` — imported
read-only, never edited.
"""

from __future__ import annotations

import re

from app.contracts.router import (
    PRECEDENCE_TOKENS,
    Delivery,
    ExtractedParams,
    Intent,
    ReportFormat,
    Segment,
)

# ---------------------------------------------------------------------------
# §2.5 deterministic intent precedence
# ---------------------------------------------------------------------------

#: The eleven report-flow intents (derived from the frozen enum, not re-listed).
_REPORT_INTENTS: frozenset[Intent] = frozenset(
    i for i in Intent if i.value.startswith("report_")
)

#: A precedence token resolves to a *general* report intent; when the model
#: already proposed a more-specific member of the same flow family, the model's
#: choice is kept so the specialization is not clobbered. ``report_ledger`` is the
#: general form of ``report_mtf_ledger``; ``report_tax`` is the general form of the
#: two Tax-flow specializations that carry education lines.
_GENERALIZES: dict[Intent, frozenset[Intent]] = {
    Intent.report_ledger: frozenset({Intent.report_mtf_ledger}),
    Intent.report_tax: frozenset({Intent.report_capital_gain, Intent.report_tax_pnl}),
}


def _token_matches(token: str, text: str) -> bool:
    """Whole-token match of a precedence token in ``text`` (both lowercased).

    Guards against short tokens (``cg``, ``pnl``) matching inside longer words by
    requiring no alphanumeric neighbour on either side. ``&`` in ``p&l`` is a
    non-word char, so the boundary check still admits ``p&l statement``."""
    pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _resolve_precedence(utterance: str, model_intent: Intent) -> Intent:
    """Apply the frozen §2.5 precedence rules after the model proposes an intent.

    The first token in the frozen ``PRECEDENCE_TOKENS`` order that whole-matches
    the utterance wins ("tax" beats "p&l"; "capital gain"/"cg" → capital gain;
    "holding statement" → holding, not ledger; bare "p&l"/"pnl" → pnl). The
    override applies only to report-vs-report disambiguation:

    - a non-report model intent (``rag_qa``, ticketing, ``smalltalk_fallback``) is
      never forced to a report;
    - a more-specific model intent is kept over its generalization
      (MTF ledger / capital gain / Tax-P&L survive their base token);
    - no matching token leaves the model's intent untouched.
    """
    if model_intent not in _REPORT_INTENTS:
        return model_intent

    text = utterance.lower()
    for token, forced in PRECEDENCE_TOKENS:
        if _token_matches(token, text):
            if model_intent in _GENERALIZES.get(forced, frozenset()):
                return model_intent
            return forced
    return model_intent


# ---------------------------------------------------------------------------
# FY / AY normalization + free-text parameter extraction
# ---------------------------------------------------------------------------

#: A financial-year range: a 4-digit start year, a separator, then a 2- or 4-digit
#: end. Validated as consecutive years so an ISO date fragment (``2024-04``) is not
#: mistaken for an FY.
_FY_RANGE_RE = re.compile(r"(\d{4})\s*[-/–—]\s*(\d{2,4})")

#: A single year explicitly qualified as an FY or AY (``FY 2025``, ``AY 2025``).
_FY_SINGLE_RE = re.compile(
    r"(?:fy|f\.y\.|financial year|ay|a\.y\.|assessment year)\s*(\d{4})(?![0-9])"
)

#: An Assessment-Year qualifier standing on its own (not inside another word).
_AY_RE = re.compile(r"(?<![a-z])(?:a\.?y\.?|assessment year)(?![a-z])")


def _is_consecutive(start: int, end_token: str) -> bool:
    """True when ``end_token`` is the year after ``start`` (2- or 4-digit form)."""
    if len(end_token) == 2:
        return int(end_token) == (start + 1) % 100
    return int(end_token) == start + 1


def parse_fy_or_ay(utterance: str) -> tuple[str | None, bool]:
    """Extract a financial year from free text, returning ``(fy_long, is_ay)``.

    ``fy_long`` is the canonical ``"YYYY-YYYY"`` form (``FY 2025-26`` → ``"2025-2026"``).
    When the utterance names an **Assessment Year**, it is converted AY→FY (AY start
    year S → FY start year S-1) and ``is_ay`` is ``True`` so the caller can flag the
    conversion for confirmation. Returns ``(None, False)`` when no financial year is
    present. Never raises."""
    text = utterance.lower()

    start: int | None = None
    m = _FY_RANGE_RE.search(text)
    if m and _is_consecutive(int(m.group(1)), m.group(2)):
        start = int(m.group(1))
    else:
        m2 = _FY_SINGLE_RE.search(text)
        if m2:
            start = int(m2.group(1))

    if start is None:
        return None, False

    is_ay = _AY_RE.search(text) is not None
    if is_ay:
        start -= 1  # Assessment Year S-(S+1) corresponds to Financial Year (S-1)-S.
    return f"{start}-{start + 1}", is_ay


def _normalize_fy(value: str) -> str:
    """Normalize a model-provided FY string to the long ``"YYYY-YYYY"`` form; leave
    an unparseable value untouched."""
    fy_long, _ = parse_fy_or_ay(value)
    return fy_long or value


#: Free-text keyword → enum tables for the augmentation pass. Ordered; the first
#: matching keyword wins. Each keyword is whole-token matched.
_SEGMENT_KEYWORDS: tuple[tuple[str, Segment], ...] = (
    ("equity", Segment.equity),
    ("equities", Segment.equity),
    ("f&o", Segment.fno),
    ("fno", Segment.fno),
    ("futures", Segment.fno),
    ("options", Segment.fno),
    ("derivatives", Segment.fno),
    ("derivative", Segment.fno),
    ("commodity", Segment.commodity),
    ("commodities", Segment.commodity),
    ("mcx", Segment.commodity),
)

_FORMAT_KEYWORDS: tuple[tuple[str, ReportFormat], ...] = (
    ("pdf", ReportFormat.pdf),
    ("excel", ReportFormat.excel),
    ("xlsx", ReportFormat.excel),
    ("xls", ReportFormat.excel),
    ("spreadsheet", ReportFormat.excel),
)

_DELIVERY_KEYWORDS: tuple[tuple[str, Delivery], ...] = (
    ("email", Delivery.email),
    ("e-mail", Delivery.email),
    ("mail it", Delivery.email),
    ("download", Delivery.in_chat),
    ("in chat", Delivery.in_chat),
    ("in-chat", Delivery.in_chat),
)


def _first_keyword(table, text: str):
    for keyword, value in table:
        if _token_matches(keyword, text):
            return value
    return None


def _extract_params(
    utterance: str, intent: Intent, model_params: ExtractedParams
) -> tuple[ExtractedParams, bool]:
    """Post-process the model's extracted parameters for a report intent.

    Deterministic FY/AY parsing is authoritative over the model's ``fy``; AY→FY sets
    the returned ``needs_confirmation``. Segment / format / delivery are augmented
    from the utterance ONLY where the model left them unset; ``date_range`` passes
    through from the model. Non-report intents carry the model's params unchanged.
    """
    params = model_params.model_copy(deep=True)
    if intent not in _REPORT_INTENTS:
        return params, False

    needs_confirmation = False
    fy_long, is_ay = parse_fy_or_ay(utterance)
    if fy_long is not None:
        params.fy = fy_long
        needs_confirmation = is_ay
    elif params.fy:
        params.fy = _normalize_fy(params.fy)

    text = utterance.lower()
    if params.segment is None:
        params.segment = _first_keyword(_SEGMENT_KEYWORDS, text)
    if params.report_format is None:
        params.report_format = _first_keyword(_FORMAT_KEYWORDS, text)
    if params.delivery is None:
        params.delivery = _first_keyword(_DELIVERY_KEYWORDS, text)

    return params, needs_confirmation
