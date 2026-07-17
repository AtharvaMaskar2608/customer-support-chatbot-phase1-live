"""Error-taxonomy mapping (proposal §Error-code mapping; 02 §8.4).

Maps typed adapter exceptions AND in-band business results to the five frozen
error codes, emitting the VERBATIM copy + recovery chips from ``app.contracts.errors``
(only the bracketed placeholders are substituted). ``Reason`` strings, HTTP codes,
and URLs NEVER appear in user copy — the mapper reads the frozen copy only, never
the exception's message.
"""

from __future__ import annotations

from app.contracts.errors import ERROR_COPY, ErrorCode
from app.contracts.flow import default_fy, fy_long_to_short, supported_fys
from app.contracts.router import ExtractedParams
from app.contracts.wire import Chip, ErrorBubble

from app.engine.chips import chip_for_label, fy_chip
from app.engine.faults import (
    FinXAuthError,
    FinXFetchError,
    FinXTimeoutError,
    FinXTransportError,
)
from app.engine.fy import normalize_fy
from app.engine.ports import EngineContext, GenerationError, NoData
from app.engine.results import EYearError

#: What ``map_error`` accepts: a typed fault or an in-band result.
Fault = (
    EYearError
    | NoData
    | GenerationError
    | FinXFetchError
    | FinXTimeoutError
    | FinXAuthError
    | FinXTransportError
    | Exception
)


def _code_for(fault: Fault) -> ErrorCode:
    if isinstance(fault, EYearError):
        return ErrorCode.E_YEAR
    if isinstance(fault, NoData):
        return ErrorCode.E_NODATA
    if isinstance(fault, FinXTimeoutError):
        return ErrorCode.E_TIMEOUT
    if isinstance(fault, FinXFetchError):
        return ErrorCode.E_FETCH
    # GenerationError, FinXAuthError, FinXTransportError, and anything else.
    return ErrorCode.E_UNKNOWN


def _bare_short(fy_long: str) -> str:
    """``"2024-2025"`` → ``"2024-25"`` (short form without the ``FY`` prefix)."""
    return fy_long_to_short(fy_long).replace("FY", "").strip()


def _humanized_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _selection_label(params: ExtractedParams | None) -> str:
    # The copy reads "for FY {FY_short}", so {FY_short} is the bare short year
    # ("2024-25") — never the "FY 2024-25" chip form, which would double the "FY".
    if params is None:
        return "that period"
    if params.fy:
        try:
            return _bare_short(normalize_fy(params.fy))
        except ValueError:
            return params.fy
    if params.date_range and (params.date_range.from_ or params.date_range.to):
        parts = [d.isoformat() for d in (params.date_range.from_, params.date_range.to) if d]
        return " – ".join(parts)
    return "that period"


def _substitute(text: str, subs: dict[str, str]) -> str:
    for key, value in subs.items():
        text = text.replace("{" + key + "}", value)
    return text


def map_error(
    fault: Fault,
    flow=None,
    *,
    ctx: EngineContext,
    params: ExtractedParams | None = None,
) -> ErrorBubble:
    """One error bubble with verbatim frozen copy + recovery chips. ``fault`` is a
    typed adapter exception or an in-band result; ``params`` supplies the selection
    used for the ``{FY_short}`` substitution."""
    code = _code_for(fault)
    spec = ERROR_COPY[code]
    today = ctx.now.date()

    subs = {
        "FY_short": _selection_label(params),
        "defaultFY": _bare_short(default_fy(today)),
        "list": _humanized_list([fy_long_to_short(f) for f in supported_fys(today)]),
    }

    # E-FETCH surfaces the verbatim SECOND line (shown only once the silent retry
    # has also failed); every other code uses its primary text.
    raw_text = spec.second_line if (code is ErrorCode.E_FETCH and spec.second_line) else spec.text
    text = _substitute(raw_text, subs)

    chips = _chips_for(code, spec, subs, fault, today)
    return ErrorBubble(code=code, text=text, chips=chips)


def _chips_for(code, spec, subs, fault, today) -> list[Chip]:
    if code is ErrorCode.E_YEAR:
        # The three in-window FY chips (from the error's own set if present).
        supported = (
            list(fault.supported)
            if isinstance(fault, EYearError) and fault.supported
            else supported_fys(today)
        )
        return [fy_chip(f) for f in supported]

    if code is ErrorCode.E_NODATA and spec.chips:
        # First chip re-selects the default FY (verbatim label, typed payload).
        first_label = _substitute(spec.chips[0], subs)
        first = chip_for_label(first_label, payload={"fy": default_fy(today)})
        rest = [chip_for_label(_substitute(lbl, subs)) for lbl in spec.chips[1:]]
        return [first, *rest]

    return [chip_for_label(_substitute(lbl, subs)) for lbl in spec.chips]
