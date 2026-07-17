"""error-taxonomy spec tests.

Asserts exactly five codes, verbatim §8.4 copy + recovery chips, the E-FETCH
silent-retry second line, EC-12 partial-email copy, and that no copy leaks
Reason/HTTP/URL detail.
"""

from __future__ import annotations

from app.contracts.errors import EC12, ERROR_COPY, ErrorCode

# Verbatim copy transcribed from the error-taxonomy spec / flow spec §8.4.
EXPECTED_COPY = {
    ErrorCode.E_NODATA: (
        "No transactions found for FY {FY_short}, so there's nothing to report "
        "for that year."
    ),
    ErrorCode.E_YEAR: (
        "I can pull Tax Reports for the current and last two financial years — "
        "that's {list}. Which one?"
    ),
    ErrorCode.E_TIMEOUT: (
        "That took longer than it should — the report didn't come through. Your "
        "selections are saved."
    ),
    ErrorCode.E_FETCH: (
        "The report generated but arrived incomplete on my side — let me redo it."
    ),
    ErrorCode.E_UNKNOWN: "Something went wrong generating that report on our side.",
}


def test_five_codes_verbatim():
    # Exactly five codes with the spec's code strings.
    assert {c.value for c in ErrorCode} == {
        "E-NODATA",
        "E-YEAR",
        "E-TIMEOUT",
        "E-FETCH",
        "E-UNKNOWN",
    }
    assert len(list(ErrorCode)) == 5
    assert set(ERROR_COPY.keys()) == set(ErrorCode)

    # Copy is verbatim.
    for code, expected in EXPECTED_COPY.items():
        assert ERROR_COPY[code].text == expected

    # E-FETCH auto-retries silently before showing the second line.
    assert ERROR_COPY[ErrorCode.E_FETCH].second_line == "Still not coming through cleanly."
    # Other codes have no second line.
    for code in (ErrorCode.E_NODATA, ErrorCode.E_YEAR, ErrorCode.E_TIMEOUT, ErrorCode.E_UNKNOWN):
        assert ERROR_COPY[code].second_line is None

    # E-YEAR renders the three FY chips dynamically.
    assert ERROR_COPY[ErrorCode.E_YEAR].dynamic_chips == "fy_window"


def test_recovery_chips_present():
    # Every code reaches raise-ticket except the FY-window one (which is the 3 FY chips).
    assert ERROR_COPY[ErrorCode.E_NODATA].chips[-1] == "🎫 Raise a ticket"
    assert ERROR_COPY[ErrorCode.E_TIMEOUT].chips == ("↺ Retry", "🎫 Raise a ticket")
    assert ERROR_COPY[ErrorCode.E_FETCH].chips == (
        "↺ Try again",
        "✉️ Email me both",
        "🎫 Raise a ticket",
    )
    assert ERROR_COPY[ErrorCode.E_UNKNOWN].chips == ("↺ Retry", "🎫 Raise a ticket")


def test_no_internal_detail_leaks():
    # Copy never exposes Reason strings, HTTP codes, or URLs.
    for spec in ERROR_COPY.values():
        text = spec.text + (spec.second_line or "")
        lowered = text.lower()
        assert "http" not in lowered
        assert "reason" not in lowered
        assert "://" not in text
        assert "401" not in text and "404" not in text


def test_ec12_partial_email_failure():
    assert EC12.text == (
        "Your PDF is on its way to {masked_email}, but the Excel didn't go through."
    )
    assert EC12.chips == ("↺ Retry Excel", "📊 Get Excel here", "🎫 Raise a ticket")
