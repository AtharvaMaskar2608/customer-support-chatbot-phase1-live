"""Task 2 — deterministic §2.5 intent precedence (no LLM).

Exercises ``_resolve_precedence`` directly against the frozen ``PRECEDENCE_TOKENS``
rules. The model's proposed intent is passed in explicitly so no classification
call happens.
"""

from __future__ import annotations

import pytest

from app.contracts.router import Intent
from app.llm.router import _resolve_precedence


@pytest.mark.parametrize(
    "utterance,model_intent,expected",
    [
        # "tax" beats "p&l".
        ("tax report or p&l", Intent.report_pnl, Intent.report_tax),
        ("send me the tax statement", Intent.report_pnl, Intent.report_tax),
        # capital gain / CG → capital gain (Tax flow member).
        ("capital gain report please", Intent.report_pnl, Intent.report_capital_gain),
        ("i need my CG statement", Intent.report_tax, Intent.report_capital_gain),
        # holding statement → holding, NOT ledger.
        ("holding statement", Intent.report_ledger, Intent.report_holding),
        # bare p&l / pnl → pnl.
        ("p&l", Intent.report_pnl, Intent.report_pnl),
        ("pnl please", Intent.report_ledger, Intent.report_pnl),
        # more-specific model intent survives its base token.
        ("mtf ledger", Intent.report_mtf_ledger, Intent.report_mtf_ledger),
        ("tax p&l for last year", Intent.report_tax_pnl, Intent.report_tax_pnl),
        ("capital gain vs tax", Intent.report_capital_gain, Intent.report_capital_gain),
        # non-report model intents are never forced to a report.
        ("how do i download my tax report", Intent.rag_qa, Intent.rag_qa),
        ("what does p&l mean", Intent.rag_qa, Intent.rag_qa),
        ("hi there", Intent.smalltalk_fallback, Intent.smalltalk_fallback),
        # no precedence token → model intent unchanged.
        ("show me contract notes", Intent.report_contract_notes, Intent.report_contract_notes),
        ("brokerage charges", Intent.report_brokerage, Intent.report_brokerage),
    ],
)
def test_resolve_precedence(utterance, model_intent, expected):
    assert _resolve_precedence(utterance, model_intent) is expected


def test_short_token_not_matched_inside_word():
    # "cg" must not match inside "recognize"; model intent is left untouched.
    assert _resolve_precedence("help me recognize my report", Intent.report_ledger) is Intent.report_ledger
    # "pnl" must not match inside a larger alphanumeric run.
    assert _resolve_precedence("openpnldata", Intent.report_ledger) is Intent.report_ledger
