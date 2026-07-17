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
    Intent,
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
