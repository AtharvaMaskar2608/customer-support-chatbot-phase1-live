"""T10: the executor `advance` end-to-end (proposal §State-machine executor / doneCondition)."""

from __future__ import annotations

from datetime import date

from app.contracts.errors import ErrorCode
from app.contracts.flow import DateWindow, StepKind, StepState
from app.contracts.router import Delivery, ExtractedParams, Intent, Segment
from app.contracts.wire import Calendar, ChipActionKind, ConversationState, ErrorBubble, FileCard, StepperCard

from app.engine.events import DateSelected, FollowUp, ParamSelected, ReopenStep, Resend
from app.engine.executor import advance
from app.engine.ports import ReportUrl
from tests.engine.conftest import FakeByteFetcher, FakeFlow, make_ctx, start_state

PDF = b"%PDF-1.7" + b"\x00" * 4000


def _pnl(**over):
    return FakeFlow(intent=Intent.report_pnl, title="P&L Statement", **over)


async def test_drives_full_flow_first_step_to_delivery():
    flow = _pnl(generate_results=[ReportUrl("https://client-report/x.pdf")])
    ctx = make_ctx(fetcher=FakeByteFetcher([PDF]))
    state = start_state(flow)

    # Turn 1: pick segment → date_range becomes active (stepper + calendar).
    r1 = await advance(state, ParamSelected(ExtractedParams(segment=Segment.equity), label="Equity"), flow, ctx=ctx)
    assert r1.conversation_state is ConversationState.collecting
    assert any(isinstance(b, StepperCard) for b in r1.blocks)
    assert any(isinstance(b, Calendar) for b in r1.blocks)
    assert flow.generate_calls == 0  # nothing generated while collecting

    # Turn 2: pick the date range → delivery becomes active (stepper, no calendar).
    r2 = await advance(r1.state, DateSelected(date(2024, 4, 1), date(2024, 6, 30)), flow, ctx=ctx)
    assert r2.conversation_state is ConversationState.collecting
    assert not any(isinstance(b, Calendar) for b in r2.blocks)

    # Turn 3: pick delivery → ready to generate → file delivered.
    r3 = await advance(r2.state, ParamSelected(ExtractedParams(delivery=Delivery.in_chat)), flow, ctx=ctx)
    assert r3.conversation_state is ConversationState.delivered
    card = next(b for b in r3.blocks if isinstance(b, FileCard))
    assert card.filename == "P&L Statement.pdf"
    assert flow.generate_calls == 1 and ctx.byte_fetcher.calls == 1
    assert r3.state.current_step is StepKind.generate


async def test_stepper_edit_clears_downstream_and_refetches_nothing():
    flow = _pnl(generate_results=[ReportUrl("u")])
    ctx = make_ctx(fetcher=FakeByteFetcher([PDF]))
    collected = ExtractedParams(segment=Segment.equity, date_range=None)
    from app.contracts.router import DateRange

    collected = ExtractedParams(
        segment=Segment.equity,
        date_range=DateRange(from_=date(2024, 4, 1), to=date(2024, 6, 30)),
    )
    state = start_state(flow, collected)  # segment + dates done, delivery active

    r = await advance(state, ReopenStep("segment"), flow, ctx=ctx)
    by_id = {s.id: s for s in r.state.steps}
    assert by_id["segment"].state is StepState.active
    assert by_id["dates"].state is StepState.pending  # downstream cleared
    assert r.state.collected.segment is None and r.state.collected.date_range is None
    assert r.conversation_state is ConversationState.collecting
    # Nothing is re-fetched on an edit — only the generation step fetches.
    assert flow.generate_calls == 0 and ctx.byte_fetcher.calls == 0


async def test_resend_bypasses_cache_and_regenerates():
    flow = _pnl(generate_results=[ReportUrl("u1"), ReportUrl("u2")])
    ctx = make_ctx(fetcher=FakeByteFetcher([PDF, PDF]))
    collected = ExtractedParams(segment=Segment.equity, delivery=Delivery.in_chat)
    from app.contracts.router import DateRange

    collected = collected.model_copy(update={"date_range": DateRange(from_=date(2024, 4, 1), to=date(2024, 6, 30))})
    state = start_state(flow, collected)

    # First delivery (fills the cache).
    delivered = await advance(state, ParamSelected(ExtractedParams()), flow, ctx=ctx)
    assert delivered.conversation_state is ConversationState.delivered
    assert flow.generate_calls == 1 and ctx.byte_fetcher.calls == 1

    # Resend bypasses the cache → regenerates + refetches.
    resent = await advance(delivered.state, Resend(), flow, ctx=ctx)
    assert resent.conversation_state is ConversationState.delivered
    assert flow.generate_calls == 2 and ctx.byte_fetcher.calls == 2


async def test_third_followup_escalates():
    flow = _pnl()
    state = start_state(flow)
    # First/second unresolved follow-ups keep collecting.
    r_ok = await advance(state, FollowUp(resolved=False), flow, ctx=make_ctx(follow_up_count=1))
    assert r_ok.escalated is False and r_ok.conversation_state is ConversationState.collecting
    # The third escalates with ticket/call chips.
    r_esc = await advance(state, FollowUp(resolved=False), flow, ctx=make_ctx(follow_up_count=2))
    assert r_esc.escalated is True and r_esc.conversation_state is ConversationState.escalated
    from app.contracts.wire import ChipRow

    chips = next(b for b in r_esc.blocks if isinstance(b, ChipRow)).chips
    assert {c.action.kind for c in chips} == {ChipActionKind.raise_ticket, ChipActionKind.call_support}


async def test_out_of_range_date_is_nudged_not_progressed():
    flow = _pnl(generate_results=[ReportUrl("u")])
    ctx = make_ctx(fetcher=FakeByteFetcher([PDF]))
    state = start_state(flow, ExtractedParams(segment=Segment.equity))  # date_range active

    from app.contracts.wire import Bubble

    r = await advance(state, DateSelected(date(2017, 1, 1), date(2017, 6, 30)), flow, ctx=ctx)  # before floor 2018
    assert any(isinstance(b, Bubble) for b in r.blocks)  # nudge
    assert r.conversation_state is ConversationState.collecting
    assert r.state.collected.date_range is None  # not accepted
    assert flow.generate_calls == 0


def _tax(**over):
    return FakeFlow(
        intent=Intent.report_tax,
        title="Tax Report",
        window=DateWindow(fy_based=True),
        step_specs=[("fy", StepKind.fy), ("gen", StepKind.generate)],
        **over,
    )


async def test_fy_out_of_window_yields_e_year_with_no_adapter_call():
    flow = _tax(generate_results=[ReportUrl("u")])
    ctx = make_ctx(fetcher=FakeByteFetcher([PDF]), now=make_ctx().now)  # today 2026-07-17
    state = start_state(flow)
    r = await advance(state, ParamSelected(ExtractedParams(fy="2020-2021")), flow, ctx=ctx)
    assert r.conversation_state is ConversationState.error
    assert isinstance(r.blocks[0], ErrorBubble) and r.blocks[0].code is ErrorCode.E_YEAR
    # No adapter call: generation was gated before deliver.
    assert flow.generate_calls == 0 and ctx.byte_fetcher.calls == 0


async def test_fy_in_window_delivers():
    flow = _tax(generate_results=[ReportUrl("u")])
    ctx = make_ctx(fetcher=FakeByteFetcher([PDF]))
    state = start_state(flow)
    r = await advance(state, ParamSelected(ExtractedParams(fy="2024-2025")), flow, ctx=ctx)
    assert r.conversation_state is ConversationState.delivered
    assert any(isinstance(b, FileCard) for b in r.blocks)
    assert flow.generate_calls == 1 and ctx.byte_fetcher.calls == 1
