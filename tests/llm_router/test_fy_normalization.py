"""Task 3 — deterministic FY/AY normalization and param extraction (no LLM).

Drives ``parse_fy_or_ay`` and ``_extract_params`` directly, using the frozen
FY helpers' long ``"YYYY-YYYY"`` form. No classification call happens.
"""

from __future__ import annotations

import pytest

from app.contracts.router import Delivery, ExtractedParams, Intent, ReportFormat, Segment
from app.llm.router import _extract_params, parse_fy_or_ay


@pytest.mark.parametrize(
    "utterance,expected_fy,expected_is_ay",
    [
        ("FY 2025-26", "2025-2026", False),
        ("financial year 2024-25", "2024-2025", False),
        ("give me tax report for 2025-26", "2025-2026", False),
        ("2025-2026", "2025-2026", False),
        # AY→FY: AY start year S maps to FY start year S-1.
        ("AY 2025-26", "2024-2025", True),
        ("assessment year 2025-2026", "2024-2025", True),
        # No financial year present.
        ("get my p&l", None, False),
        # An ISO date fragment must NOT be read as an FY (non-consecutive years).
        ("from 2024-04 to 2025-03", None, False),
    ],
)
def test_parse_fy_or_ay(utterance, expected_fy, expected_is_ay):
    assert parse_fy_or_ay(utterance) == (expected_fy, expected_is_ay)


def test_extract_params_fy_authoritative_and_confirmation():
    # Deterministic FY overrides the model's raw string; long form emitted.
    params, needs = _extract_params(
        "tax report FY 2025-26", Intent.report_tax, ExtractedParams(fy="FY 2025-26")
    )
    assert params.fy == "2025-2026"
    assert needs is False

    # AY→FY sets needs_confirmation.
    params, needs = _extract_params(
        "tax report for AY 2025-26", Intent.report_tax, ExtractedParams()
    )
    assert params.fy == "2024-2025"
    assert needs is True


def test_extract_params_normalizes_model_fy_without_utterance_year():
    # Utterance has no year token but the model returned a short FY → normalize it.
    params, needs = _extract_params(
        "my tax report", Intent.report_tax, ExtractedParams(fy="FY 2024-25")
    )
    assert params.fy == "2024-2025"
    assert needs is False


def test_extract_params_augments_only_unset_fields():
    # Model set segment; delivery/format come from the utterance keywords.
    params, _ = _extract_params(
        "equity p&l as excel, email it",
        Intent.report_pnl,
        ExtractedParams(segment=Segment.equity),
    )
    assert params.segment is Segment.equity
    assert params.report_format is ReportFormat.excel
    assert params.delivery is Delivery.email

    # Model's explicit value is never overwritten by augmentation.
    params, _ = _extract_params(
        "send my p&l as excel",
        Intent.report_pnl,
        ExtractedParams(report_format=ReportFormat.pdf),
    )
    assert params.report_format is ReportFormat.pdf


def test_extract_params_noop_for_non_report_intent():
    # rag_qa / smalltalk keep the model's params; no spurious augmentation.
    params, needs = _extract_params(
        "what are my options worth", Intent.rag_qa, ExtractedParams()
    )
    assert params.segment is None
    assert params.fy is None
    assert needs is False
