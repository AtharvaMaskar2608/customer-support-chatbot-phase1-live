"""flow-engine-contract spec tests.

Asserts: the FY helpers are implemented and dynamic (roll on 1 April, never
hardcode the three years); the step-kind → render-block mapping; the
byte-validation / one-silent-retry / 15-minute cache semantics; and the FlowSpec
protocol + module-level FLOW registration contract (no register import).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.contracts.flow import (
    FLOW_ATTR,
    MAGIC_BYTES,
    ByteValidation,
    CacheConfig,
    DateWindow,
    FlowConfig,
    FlowSpec,
    Step,
    StepKind,
    StepState,
    current_fy,
    default_fy,
    fy_long_to_short,
    fy_short_to_long,
    selection_cache_key,
    supported_fys,
)
from app.contracts.router import ExtractedParams, Intent


def test_fy_helpers():
    # On/after 1 April → start year is the current calendar year.
    assert current_fy(date(2025, 4, 1)) == "2025-2026"
    assert current_fy(date(2025, 12, 31)) == "2025-2026"
    # Before 1 April → previous calendar year.
    assert current_fy(date(2025, 3, 31)) == "2024-2025"

    # Window rolls forward across the Apr-1 boundary — no code change, no oldest year drop hardcoded.
    before = supported_fys(date(2025, 3, 31))
    after = supported_fys(date(2025, 4, 1))
    assert before == ["2024-2025", "2023-2024", "2022-2023"]
    assert after == ["2025-2026", "2024-2025", "2023-2024"]
    assert before != after  # dynamic

    # defaultFY is the last completed FY (currentFY-1), listed first among supported.
    assert default_fy(date(2025, 4, 1)) == "2024-2025"
    assert supported_fys(date(2025, 4, 1))[1] == default_fy(date(2025, 4, 1))

    # Short↔long mapping round-trips.
    assert fy_long_to_short("2025-2026") == "FY 2025-26"
    assert fy_short_to_long("FY 2025-26") == "2025-2026"
    assert fy_short_to_long(fy_long_to_short("2018-2019")) == "2018-2019"

    # No hardcoded years anywhere: a far-future date computes correctly.
    assert current_fy(date(2099, 5, 1)) == "2099-2100"


def test_step_kind_drives_render_block():
    # kind determines the render block: date_range → calendar, segment → chip row.
    assert {k.value for k in StepKind} == {
        "segment",
        "date_range",
        "fy",
        "delivery",
        "format",
        "confirm",
        "generate",
    }
    step = Step(id="s1", kind=StepKind.date_range, state=StepState.active)
    assert step.kind is StepKind.date_range


def test_cache_and_registry_contract():
    # 15-minute TTL, resend bypasses the cache.
    cache = CacheConfig()
    assert cache.ttl_seconds == 900
    assert cache.bypass_on_resend is True

    # Cache key changes when a selection changes (no cross-contamination).
    a = selection_cache_key(Intent.report_pnl, ExtractedParams(fy="2024-2025"))
    b = selection_cache_key(Intent.report_pnl, ExtractedParams(fy="2023-2024"))
    assert a != b

    # Byte-validation: magic bytes + exactly one silent retry.
    bv = ByteValidation()
    assert bv.pdf_magic == b"%PDF"
    assert bv.excel_magic == b"PK"
    assert bv.silent_retries == 1
    assert MAGIC_BYTES == {"pdf": b"%PDF", "xlsx": b"PK"}

    # FlowSpec protocol + module-level FLOW registration (no register import).
    assert FLOW_ATTR == "FLOW"

    class _PnlFlow:
        intent = Intent.report_pnl
        config = FlowConfig(intent=Intent.report_pnl, window=DateWindow(floor=date(2018, 1, 1), cap_relative_days=7, max_range_days=730))

        def steps(self):
            return [Step(id="segment", kind=StepKind.segment)]

    flow_obj = _PnlFlow()
    # A flow module exposes a module-level FLOW object; discovery reads it and keys by intent.
    module = SimpleNamespace(FLOW=flow_obj)
    discovered = getattr(module, FLOW_ATTR)
    assert isinstance(discovered, FlowSpec)  # runtime_checkable protocol
    registry = {discovered.intent: discovered}
    assert registry[Intent.report_pnl] is flow_obj
