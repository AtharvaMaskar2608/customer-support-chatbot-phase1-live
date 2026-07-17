"""T2: step progression + stepper-edit semantics (proposal §Step progression / §8.4)."""

from __future__ import annotations

from datetime import date

from app.contracts.flow import StepKind, StepState
from app.contracts.router import DateRange, Delivery, ExtractedParams, Segment
from app.contracts.wire import StepState as WireStepState

from app.engine.steps import build_stepper_card, next_step, reopen_step
from tests.engine.conftest import FakeFlow, make_ctx, start_state


def test_next_step_returns_first_incomplete():
    flow = FakeFlow()
    state = start_state(flow)
    step = next_step(state, flow)
    assert step is not None and step.id == "segment"


def test_next_step_prefills_router_extracted_params():
    # A step already satisfied by the router's ExtractedParams is skipped.
    flow = FakeFlow()
    state = start_state(flow, ExtractedParams(segment=Segment.equity))
    step = next_step(state, flow)
    assert step is not None and step.kind is StepKind.date_range
    # The satisfied segment step is materialized as done with a derived label.
    seg = next(s for s in state.steps if s.id == "segment")
    assert seg.state is StepState.done and seg.selected_label == "Equity"


def test_next_step_none_when_ready_to_generate():
    flow = FakeFlow()
    collected = ExtractedParams(
        segment=Segment.equity,
        date_range=DateRange(from_=date(2024, 4, 1), to=date(2024, 6, 30)),
        delivery=Delivery.in_chat,
    )
    state = start_state(flow, collected)
    assert next_step(state, flow) is None  # only the terminal generate step remains


def test_reopen_clears_downstream_preserves_upstream():
    flow = FakeFlow()
    collected = ExtractedParams(
        segment=Segment.equity,
        date_range=DateRange(from_=date(2024, 4, 1), to=date(2024, 6, 30)),
        delivery=Delivery.in_chat,
    )
    state = start_state(flow, collected).model_copy(update={"cache_key": "pnl:stale"})

    reopened = reopen_step(state, "dates")

    by_id = {s.id: s for s in reopened.steps}
    # Upstream preserved.
    assert by_id["segment"].state is StepState.done
    assert reopened.collected.segment is Segment.equity
    # Target reopened, its label cleared.
    assert by_id["dates"].state is StepState.active
    assert by_id["dates"].selected_label is None
    assert reopened.collected.date_range is None
    # Downstream cleared.
    assert by_id["delivery"].state is StepState.pending
    assert reopened.collected.delivery is None
    # Cache invalidated — nothing is re-fetched until generation.
    assert reopened.cache_key is None


def test_reopen_unknown_step_raises():
    flow = FakeFlow()
    state = start_state(flow)
    try:
        reopen_step(state, "does-not-exist")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError for unknown step id")


def test_stepper_card_marks_done_tappable_and_active_has_chips():
    flow = FakeFlow()
    state = start_state(flow, ExtractedParams(segment=Segment.equity))
    card = build_stepper_card(state, flow, make_ctx())

    rows = {r.id: r for r in card.steps}
    # generate (terminal) is not a stepper row.
    assert set(rows) == {"segment", "dates", "delivery"}
    # Done step keeps its label (widget renders it tappable to reopen).
    assert rows["segment"].state is WireStepState.done
    assert rows["segment"].selected_label == "Equity"
    assert rows["segment"].chips == []
    # Active step carries its choice chips.
    assert rows["dates"].state is WireStepState.active
    assert rows["dates"].chips
