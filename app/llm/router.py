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
from datetime import date

from app.config.schema import Limits
from app.contracts.flow import current_fy, fy_short_to_long, supported_fys
from app.contracts.router import (
    PRECEDENCE_TOKENS,
    ROUTE_TOOL_CHOICE,
    ROUTE_TOOL_NAME,
    TAX_FLOW_INTENTS,
    ConversationContext,
    Delivery,
    ExtractedParams,
    Intent,
    Language,
    ReportFormat,
    RouterResult,
    Segment,
    transport_failure_result,
)
from app.contracts.tools import TOOLS_BY_NAME
from app.llm.client import LLMClient
from app.llm.prompts import education_line, load_system_prompt

#: The remote-config follow-up cap (frozen default = 2). At this many prior
#: follow-ups the router stops proposing and signals escalation; the cross-turn
#: count itself is incremented by the orchestrator, never here.
DEFAULT_FOLLOW_UP_CAP: int = Limits().follow_up_cap

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
    """Whole-token match of a keyword in ``text`` (both lowercased), tolerant of a
    trailing plural ``s``.

    Guards against short tokens (``cg``, ``pnl``) matching inside longer words by
    requiring no alphanumeric neighbour on either side. ``&`` in ``p&l`` is a
    non-word char, so the boundary check still admits ``p&l statement``. The
    optional trailing ``s`` lets the frozen singular precedence tokens match the
    dominant plural phrasings ("capital gains", "contract notes", "ledgers")."""
    pattern = rf"(?<![a-z0-9]){re.escape(token)}s?(?![a-z0-9])"
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

#: A single year explicitly qualified as an FY (``FY 2025``, ``financial year 2025``).
_FY_SINGLE_RE = re.compile(r"(?:fy|f\.y\.|financial year)\s*(\d{4})(?![0-9])")

#: An Assessment Year whose qualifier DIRECTLY precedes the year — proximity-scoped
#: so a stray interjection ("ay yes …") never flips a plain FY into an AY. The
#: leading ``(?<![a-z])`` also stops words that merely END in "ay" ("may", "friday",
#: "display") being read as an AY qualifier. Matches both ``AY 2025-26`` (range) and
#: ``AY 2025`` (single); the start year is group 1.
_AY_QUALIFIER = r"(?<![a-z])(?:a\.?y\.?|assessment year)\s*"
_AY_RANGE_RE = re.compile(_AY_QUALIFIER + r"(\d{4})\s*[-/–—]\s*\d{2,4}")
_AY_SINGLE_RE = re.compile(_AY_QUALIFIER + r"(\d{4})(?![0-9])")

#: Relative financial-year references, resolved against the frozen supported-FY
#: window (``supported_fys() == [currentFY, -1, -2]``). Each maps to an index into
#: that list, so the Apr-1 rollover logic lives in the frozen helper, never here.
_RELATIVE_FY_RE: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\b(?:this|current)\s+(?:financial\s+year|fy|year)\b"), 0),
    (re.compile(r"\bcurrent\s+fy\b"), 0),
    (re.compile(r"\b(?:last|previous|prev)\s+(?:financial\s+year|fy|year)\b"), 1),
    (re.compile(r"\byear\s+before\s+last\b"), 2),
    (re.compile(r"\btwo\s+years?\s+ago\b"), 2),
)


def _is_consecutive(start: int, end_token: str) -> bool:
    """True when ``end_token`` is the year after ``start`` (2- or 4-digit form)."""
    if len(end_token) == 2:
        return int(end_token) == (start + 1) % 100
    return int(end_token) == start + 1


def _start_to_long(start_year: int) -> str:
    """Canonical long ``"YYYY-YYYY"`` form for a financial year START year, via the
    FROZEN ``fy_short_to_long`` mapping helper (so the mapping exists exactly once)."""
    return fy_short_to_long(f"FY {start_year}-{(start_year + 1) % 100:02d}")


def _relative_fy(text: str, today: date | None) -> str | None:
    """Resolve a relative FY reference ("this/current year", "last year", …) against
    the FROZEN FY helpers. "This/current year" is ``current_fy`` directly; older
    references index the ``supported_fys`` window. Returns the long-form FY or
    ``None``."""
    for pattern, index in _RELATIVE_FY_RE:
        if pattern.search(text):
            if index == 0:
                return current_fy(today)
            return supported_fys(today)[index]  # [currentFY, currentFY-1, currentFY-2]
    return None


def parse_fy_or_ay(utterance: str, today: date | None = None) -> tuple[str | None, bool]:
    """Extract a financial year from free text, returning ``(fy_long, is_ay)``.

    ``fy_long`` is the canonical ``"YYYY-YYYY"`` form produced by the FROZEN
    ``flow`` FY helpers (``FY 2025-26`` → ``"2025-2026"``). Relative references
    ("this/current year", "last year") resolve against the frozen ``supported_fys``
    window (which itself computes ``currentFY`` with the Apr-1 rollover). When the
    utterance names an **Assessment Year**, it is converted AY→FY (AY start year S →
    FY start year S-1) and ``is_ay`` is ``True`` so the caller can flag the
    conversion for confirmation. Returns ``(None, False)`` when no financial year is
    present. Never raises."""
    text = utterance.lower()

    relative = _relative_fy(text, today)
    if relative is not None:
        return relative, False

    # Assessment Year first (qualifier must directly precede the year).
    ay = _AY_RANGE_RE.search(text) or _AY_SINGLE_RE.search(text)
    if ay:
        # AY start year S-(S+1) corresponds to Financial Year (S-1)-S.
        return _start_to_long(int(ay.group(1)) - 1), True

    # Financial year: the first range whose two years are consecutive (so an ISO
    # date fragment like 2024-04 is skipped, even when a real FY follows it), else
    # an FY-qualified single year.
    for m in _FY_RANGE_RE.finditer(text):
        if _is_consecutive(int(m.group(1)), m.group(2)):
            return _start_to_long(int(m.group(1))), False

    m2 = _FY_SINGLE_RE.search(text)
    if m2:
        return _start_to_long(int(m2.group(1))), False

    return None, False


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
    utterance: str,
    intent: Intent,
    model_params: ExtractedParams,
    today: date | None = None,
) -> tuple[ExtractedParams, bool]:
    """Post-process the model's extracted parameters for a report intent.

    FY is a parameter of the Tax-flow reports only (the frozen ``TaxReportInput`` is
    the sole tool carrying ``fy``; P&L / Ledger / Contract-Notes are date-range
    flows), so deterministic FY/AY parsing runs only for ``TAX_FLOW_INTENTS``. There
    it is authoritative over the model's ``fy`` and AY→FY sets ``needs_confirmation``
    (including when the AY reaches the router only via the model's ``fy`` field).
    Segment / format / delivery are augmented from the utterance ONLY where the
    model left them unset; ``date_range`` passes through from the model. Non-report
    intents carry the model's params unchanged. ``today`` is injectable so
    relative-FY resolution is deterministic under test.
    """
    params = model_params.model_copy(deep=True)
    if intent not in _REPORT_INTENTS:
        return params, False

    needs_confirmation = False
    if intent in TAX_FLOW_INTENTS:
        fy_long, is_ay = parse_fy_or_ay(utterance, today)
        if fy_long is None and params.fy:
            # No FY in the utterance, but the model carried one — normalize it and
            # keep its AY flag so an AY→FY conversion never loses its confirmation.
            fy_long, is_ay = parse_fy_or_ay(params.fy, today)
        if fy_long is not None:
            params.fy = fy_long
            needs_confirmation = is_ay

    text = utterance.lower()
    if params.segment is None:
        params.segment = _first_keyword(_SEGMENT_KEYWORDS, text)
    if params.report_format is None:
        params.report_format = _first_keyword(_FORMAT_KEYWORDS, text)
    if params.delivery is None:
        params.delivery = _first_keyword(_DELIVERY_KEYWORDS, text)

    return params, needs_confirmation


# ---------------------------------------------------------------------------
# §8.5 language detection + sticky-language rule
# ---------------------------------------------------------------------------

#: Devanagari block — any character here marks Hindi script.
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")

#: Distinctive romanized-Hindi markers whose presence in an otherwise-Latin
#: utterance marks Hinglish (code-mixed). Deliberately excludes short tokens that
#: collide with common English words ("do", "de", "ka", "ki") so a plain English
#: sentence ("how do i download my report") is never misread as Hinglish.
_HINGLISH_MARKERS: frozenset[str] = frozenset(
    {
        "chahiye",
        "chaiye",
        "hai",
        "kaise",
        "kya",
        "mera",
        "meri",
        "mujhe",
        "karo",
        "batao",
        "dikhao",
        "nahi",
        "bhej",
        "bhai",
        "chaahiye",
    }
)


def _detect_language(utterance: str) -> Language:
    """Heuristic language detection: Devanagari → Hindi; romanized-Hindi markers in
    Latin text → Hinglish; otherwise English."""
    if _DEVANAGARI_RE.search(utterance):
        return Language.hindi
    tokens = set(re.findall(r"[a-z]+", utterance.lower()))
    if tokens & _HINGLISH_MARKERS:
        return Language.hinglish
    return Language.english


def _resolve_language(
    utterance: str,
    ctx: ConversationContext,
    model_language: Language | None = None,
) -> Language:
    """Resolve this turn's language and persist the sticky state on ``ctx`` (§8.5).

    Once English is seen the conversation locks to English thereafter; Hindi and
    Hinglish do not lock. The sticky state (``detected_language`` +
    ``language_locked``) is written back onto the ``ConversationContext`` so the
    next turn honours it; the returned value is this turn's language (also emitted
    on ``RouterResult.detected_language``)."""
    detected = model_language or _detect_language(utterance)
    if ctx.language_locked or detected is Language.english:
        result = Language.english
    else:
        result = detected

    ctx.detected_language = result
    if result is Language.english:
        ctx.language_locked = True
    return result


# ---------------------------------------------------------------------------
# One-shot follow-up + cap escalation
# ---------------------------------------------------------------------------


def _resolve_follow_up(
    ctx: ConversationContext,
    model_follow_up: str | None,
    model_escalate: bool,
    follow_up_cap: int = DEFAULT_FOLLOW_UP_CAP,
) -> tuple[str | None, bool]:
    """Resolve this turn's follow-up question and escalation flag.

    The router READS the running ``ctx.follow_up_count`` and, once it has reached
    the remote-config cap, emits no follow-up and signals ``escalate`` (route to
    ticket / call-support). Below the cap it passes the model's single follow-up
    through (at most one per turn) and respects the model's own ``escalate``. The
    router never increments the cross-turn count — that is orchestrator-owned."""
    if ctx.follow_up_count >= follow_up_cap:
        return None, True
    return model_follow_up, bool(model_escalate)


# ---------------------------------------------------------------------------
# Classifier (forced native tool call) + route() assembly
# ---------------------------------------------------------------------------


class Router:
    """The thin LLM router. Holds an injectable ``LLMClient`` (tests pass a fake
    that replays recorded ``tool_use`` blocks) and the follow-up cap. The Anthropic
    client is built lazily inside ``LLMClient``; constructing a ``Router`` performs
    no network I/O."""

    def __init__(
        self,
        client: LLMClient | None = None,
        follow_up_cap: int = DEFAULT_FOLLOW_UP_CAP,
    ) -> None:
        self.client = client or LLMClient()
        self.follow_up_cap = follow_up_cap

    def _classify(self, utterance: str, ctx: ConversationContext) -> RouterResult:
        """One forced ``route`` tool call. ``RouterResult`` materializes from the
        API-validated ``tool_use.input`` — never parsed from free-text JSON. Raises
        when the response carries no ``route`` block (treated as a transport
        failure by ``route``).

        ``ctx`` is part of the spec'd classifier signature, but its
        ``history`` is a list of ``TurnRef`` (turn ids/numbers only — no message
        content in the frozen contract), so there is no prior-turn text to send to
        the model here; every ctx-derived behaviour (sticky-language, follow-up cap)
        is applied deterministically in ``route`` after classification."""
        route_tool = TOOLS_BY_NAME[ROUTE_TOOL_NAME].model_dump()
        response = self.client.complete(
            messages=[{"role": "user", "content": utterance}],
            system=load_system_prompt(),
            tools=[route_tool],
            tool_choice=ROUTE_TOOL_CHOICE,
        )
        blocks = [
            b for b in response.tool_use if getattr(b, "name", None) == ROUTE_TOOL_NAME
        ]
        if not blocks:
            raise ValueError("router: no route tool_use block in response")
        return RouterResult.model_validate(blocks[0].input)

    def route(self, utterance: str, ctx: ConversationContext) -> RouterResult:
        """Classify ``utterance`` and run the deterministic post-layers.

        On any API/transport failure (or a missing/invalid ``route`` block) returns
        the frozen ``transport_failure_result()`` — there is no JSON-repair step,
        because strict tool use makes a successful response API-validated."""
        try:
            raw = self._classify(utterance, ctx)
        except Exception:
            return transport_failure_result()

        intent = _resolve_precedence(utterance, raw.intent)
        params, needs_confirmation = _extract_params(utterance, intent, raw.extracted_params)
        language = _resolve_language(utterance, ctx, raw.detected_language)
        follow_up, escalate = _resolve_follow_up(
            ctx, raw.follow_up_question, raw.escalate, self.follow_up_cap
        )
        return RouterResult(
            intent=intent,
            extracted_params=params,
            needs_confirmation=needs_confirmation,
            follow_up_question=follow_up,
            detected_language=language,
            escalate=escalate,
            education_line=education_line(intent),
        )


def route(
    utterance: str,
    ctx: ConversationContext,
    *,
    client: LLMClient | None = None,
) -> RouterResult:
    """Module-level router entry point (the frozen ``route`` contract surface):
    ``route(utterance, ctx) -> RouterResult``. ``client`` is a keyword-only
    injection hook for the offline test fake; production leaves it ``None`` so a
    default pinned-model ``LLMClient`` is used."""
    return Router(client=client).route(utterance, ctx)
