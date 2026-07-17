"""Error taxonomy (error-taxonomy capability).

Exactly five conversational error codes with verbatim user-facing copy and
recovery-chip sets (flow spec §8.4), plus the EC-12 partial dual-format
email-failure copy. Shared config reused by every flow. Copy is verbatim; only
the bracketed placeholders ({FY_short}, {defaultFY}, {list}, {masked_email}) are
substituted at render time. Error copy never exposes Reason strings, HTTP codes,
or URLs — the raw Reason is logged verbatim server-side only.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(str, Enum):
    """The five conversational error codes (exactly five)."""

    E_NODATA = "E-NODATA"  # API failure meaning no data in range
    E_YEAR = "E-YEAR"  # requested FY outside window, no API call
    E_TIMEOUT = "E-TIMEOUT"  # API / byte-fetch timeout / network failure
    E_FETCH = "E-FETCH"  # Status: Success but URL 404s / empty / wrong magic bytes
    E_UNKNOWN = "E-UNKNOWN"  # any other Status != "Success"


class ErrorSpec(BaseModel):
    """One error code's user-facing copy and recovery-chip set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ErrorCode
    text: str
    # E-FETCH shows a first line during the silent auto-retry, then this second
    # line only if the retry also fails.
    second_line: str | None = None
    # Verbatim recovery-chip labels. Empty when the chips are computed at render
    # time (see dynamic_chips).
    chips: tuple[str, ...] = ()
    # E-YEAR renders the three in-window FY chips, computed from the FY helpers.
    dynamic_chips: str | None = None


#: The five error codes → verbatim copy + recovery chips (flow spec §8.4).
ERROR_COPY: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.E_NODATA: ErrorSpec(
        code=ErrorCode.E_NODATA,
        text=(
            "No transactions found for FY {FY_short}, so there's nothing to "
            "report for that year."
        ),
        chips=("Try FY {defaultFY} (or another in-window year)", "🎫 Raise a ticket"),
    ),
    ErrorCode.E_YEAR: ErrorSpec(
        code=ErrorCode.E_YEAR,
        text=(
            "I can pull Tax Reports for the current and last two financial "
            "years — that's {list}. Which one?"
        ),
        dynamic_chips="fy_window",  # the 3 FY chips
    ),
    ErrorCode.E_TIMEOUT: ErrorSpec(
        code=ErrorCode.E_TIMEOUT,
        text=(
            "That took longer than it should — the report didn't come through. "
            "Your selections are saved."
        ),
        chips=("↺ Retry", "🎫 Raise a ticket"),
    ),
    ErrorCode.E_FETCH: ErrorSpec(
        code=ErrorCode.E_FETCH,
        text="The report generated but arrived incomplete on my side — let me redo it.",
        second_line="Still not coming through cleanly.",
        chips=("↺ Try again", "✉️ Email me both", "🎫 Raise a ticket"),
    ),
    ErrorCode.E_UNKNOWN: ErrorSpec(
        code=ErrorCode.E_UNKNOWN,
        text="Something went wrong generating that report on our side.",
        chips=("↺ Retry", "🎫 Raise a ticket"),
    ),
}


class Ec12PartialEmailFailure(BaseModel):
    """EC-12: partial dual-format email failure (all email-capable flows). The
    email SHALL be masked before display."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = (
        "Your PDF is on its way to {masked_email}, but the Excel didn't go through."
    )
    chips: tuple[str, ...] = Field(
        default=("↺ Retry Excel", "📊 Get Excel here", "🎫 Raise a ticket")
    )


#: The EC-12 partial-email-failure spec (single shared instance).
EC12: Ec12PartialEmailFailure = Ec12PartialEmailFailure()
