"""Task 3 — deterministic FY/AY normalization and param extraction (no LLM).

Drives ``parse_fy_or_ay`` and ``_extract_params`` directly, using the frozen
FY helpers' long ``"YYYY-YYYY"`` form. No classification call happens.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.contracts.flow import current_fy, supported_fys
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
        # A stray "ay" interjection must NOT flip a plain FY into an AY.
        ("ay yes give me tax report 2024-25", "2024-2025", False),
        # A valid FY after a non-consecutive ISO fragment is still found.
        ("from 2024-04 to report 2024-2025", "2024-2025", False),
    ],
)
def test_parse_fy_or_ay(utterance, expected_fy, expected_is_ay):
    assert parse_fy_or_ay(utterance) == (expected_fy, expected_is_ay)


def test_relative_fy_resolves_against_frozen_helpers():
    # Fixed "today" so relative resolution is deterministic. 2025-08-01 → FY 2025-2026.
    today = date(2025, 8, 1)
    window = supported_fys(today)  # [2025-2026, 2024-2025, 2023-2024]
    assert parse_fy_or_ay("tax report for this financial year", today) == (current_fy(today), False)
    assert parse_fy_or_ay("tax report for last year", today) == (window[1], False)
    assert parse_fy_or_ay("tax for the year before last", today) == (window[2], False)
    # Sanity: the "this year" answer equals the frozen current FY.
    assert current_fy(today) == "2025-2026"


def test_explicit_fy_uses_frozen_long_form():
    # "FY 2025-26" normalizes via the frozen fy_short_to_long → canonical long form.
    from app.contracts.flow import fy_short_to_long

    fy_long, is_ay = parse_fy_or_ay("tax report FY 2025-26")
    assert fy_long == fy_short_to_long("FY 2025-26") == "2025-2026"
    assert is_ay is False


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
