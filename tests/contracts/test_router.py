"""router-contract spec tests.

Asserts the promises in specs/router-contract/spec.md: the complete 16-value
Intent enum (incl. the two BLOCKED intents), the RouterResult fields and the
follow-up-cap/escalate behaviour, and the deterministic precedence constants.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.contracts.router import (
    BLOCKED_INTENTS,
    EDUCATION_LINE_INTENTS,
    PRECEDENCE_TOKENS,
    TAX_FLOW_INTENTS,
    ConversationContext,
    DateRange,
    Delivery,
    ExtractedParams,
    Intent,
    Language,
    ReportFormat,
    RouterResult,
    Segment,
)

# The 16 frozen intents named in "Requirement: Complete Intent enum".
EXPECTED_INTENTS = {
    "report_pnl",
    "report_ledger",
    "report_mtf_ledger",
    "report_contract_notes",
    "report_tax",
    "report_capital_gain",
    "report_tax_pnl",
    "report_cml",
    "report_brokerage",
    "report_holding",
    "report_global_detail",
    "rag_qa",
    "raise_ticket",
    "ticket_status",
    "call_support",
    "smalltalk_fallback",
}


def test_intent_enum_complete():
    # Exactly sixteen values, matching the spec set verbatim.
    values = {i.value for i in Intent}
    assert len(list(Intent)) == 16
    assert values == EXPECTED_INTENTS
    # Blocked intents are classifiable enum values.
    assert Intent.report_holding in BLOCKED_INTENTS
    assert Intent.report_global_detail in BLOCKED_INTENTS
    assert len(BLOCKED_INTENTS) == 2


def test_router_result_fields():
    # "Requirement: Router result fields and follow-up cap" — all seven fields.
    r = RouterResult(intent=Intent.report_pnl)
    # Defaults: unambiguous → no follow-up, no escalation, no confirmation.
    assert r.follow_up_question is None
    assert r.escalate is False
    assert r.needs_confirmation is False
    assert r.education_line is None
    assert r.detected_language is None
    assert isinstance(r.extracted_params, ExtractedParams)

    # Follow-up cap reached → escalate true (routes to ticket / call-support).
    escalated = RouterResult(intent=Intent.report_tax, escalate=True)
    assert escalated.escalate is True

    # AY→FY case sets needs_confirmation.
    conf = RouterResult(intent=Intent.report_tax, needs_confirmation=True)
    assert conf.needs_confirmation is True

    # education_line carried for CG / Tax-P&L.
    edu = RouterResult(
        intent=Intent.report_capital_gain,
        education_line="Capital Gain uses your Tax Report.",
    )
    assert edu.education_line


def test_extracted_params_optional_and_customer_facing():
    # "Parameters are optional" — empty params validate with everything absent.
    p = ExtractedParams()
    assert p.fy is None and p.segment is None and p.date_range is None
    # "Segment stays customer-facing" — Segment enum, never an API group string.
    assert {s.value for s in Segment} == {"equity", "fno", "commodity"}
    assert {f.value for f in ReportFormat} == {"pdf", "excel"}
    assert {d.value for d in Delivery} == {"in_chat", "email"}
    # date_range uses from/to aliases.
    dr = DateRange.model_validate({"from": "2024-04-01", "to": "2025-03-31"})
    assert dr.from_ == date(2024, 4, 1) and dr.to == date(2025, 3, 31)
    assert set(dr.model_dump(by_alias=True).keys()) == {"from", "to"}


def test_precedence_constants():
    # "Requirement: Intent precedence rules" encoded deterministically.
    order = [intent for _, intent in PRECEDENCE_TOKENS]
    tokens = [tok for tok, _ in PRECEDENCE_TOKENS]

    # tax beats p&l: the tax token appears before the pnl token.
    assert order.index(Intent.report_tax) < order.index(Intent.report_pnl)
    # "holding statement" resolves to report_holding, NOT report_ledger.
    holding_idx = tokens.index("holding statement")
    assert order[holding_idx] is Intent.report_holding
    assert order[holding_idx] is not Intent.report_ledger
    # capital gain / cg → the Tax flow.
    assert Intent.report_capital_gain in TAX_FLOW_INTENTS
    assert Intent.report_tax_pnl in TAX_FLOW_INTENTS
    assert Intent.report_tax in TAX_FLOW_INTENTS
    # CG and Tax-P&L carry an education line.
    assert Intent.report_capital_gain in EDUCATION_LINE_INTENTS
    assert Intent.report_tax_pnl in EDUCATION_LINE_INTENTS


def test_conversation_context_hides_secrets():
    # session_id / access_token retained on the object but never serialized.
    ctx = ConversationContext(
        user_id="X008593",
        session_id="SECRET_SESSION",
        access_token="SECRET_JWT",
        platform="web",
        page="support",
        turn_number=2,
        follow_up_count=1,
        detected_language=Language.english,
        language_locked=True,
    )
    assert ctx.session_id == "SECRET_SESSION"  # accessible in-process
    dumped = ctx.model_dump()
    assert "session_id" not in dumped and "access_token" not in dumped
    assert "SECRET_SESSION" not in ctx.model_dump_json()
    assert "SECRET_JWT" not in ctx.model_dump_json()
    # follow-up + language state are exposed to the router.
    assert dumped["turn_number"] == 2
    assert dumped["follow_up_count"] == 1
    assert dumped["language_locked"] is True


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        RouterResult(intent=Intent.report_pnl, bogus="x")
