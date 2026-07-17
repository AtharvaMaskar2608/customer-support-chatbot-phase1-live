"""Structured UI events drive the engine deterministically with NO Claude call."""

from __future__ import annotations

from app.contracts.flow import FlowState, StepKind
from app.contracts.router import ExtractedParams, Intent
from app.contracts.wire import ChipAction, ChipActionKind, FileCard, StepperCard
from app.orchestrator.ports import StepResult
from tests.orchestrator.conftest import bootstrap, make_orchestrator, turn_request
from tests.orchestrator.fakes import FakeEngine, FakeLLM, FakeTicketing


def _seed_active_flow(orch, thread_id, intent=Intent.report_pnl):
    state = orch.sessions.get(thread_id)
    state.flow_state = FlowState(intent=intent, current_step=StepKind.segment, collected=ExtractedParams())
    orch.sessions.put(thread_id, state)


def test_select_param_drives_engine_without_llm_call():
    llm = FakeLLM()  # raises if complete() is ever called
    engine = FakeEngine(StepResult(blocks=[StepperCard(steps=[])], next_state=None))
    orch, _ = make_orchestrator(llm=llm, engine=engine)
    thread_id = bootstrap(orch)
    _seed_active_flow(orch, thread_id)

    action = ChipAction(kind=ChipActionKind.select_param, payload={"segment": "equity"})
    resp = orch.handle_turn(turn_request(thread_id, action=action))

    assert llm.calls == []  # NO Claude call on a structured event
    assert engine.calls, "the engine advanced the flow"
    assert any(b.type == "stepper_card" for b in resp.blocks)


def test_open_calendar_event_drives_engine_without_llm():
    llm = FakeLLM()
    engine = FakeEngine(StepResult(blocks=[FileCard(filename="f.pdf", size_label="1 KB", format="pdf")]))
    orch, _ = make_orchestrator(llm=llm, engine=engine)
    thread_id = bootstrap(orch)
    _seed_active_flow(orch, thread_id)

    action = ChipAction(kind=ChipActionKind.open_calendar, payload={})
    orch.handle_turn(turn_request(thread_id, action=action))
    assert llm.calls == []
    assert len(engine.calls) == 1


def test_raise_ticket_chip_binds_client_id_from_session_no_llm():
    llm = FakeLLM()
    ticketing = FakeTicketing(ticket_id="T-901")
    orch, _ = make_orchestrator(llm=llm, ticketing=ticketing)
    thread_id = bootstrap(orch)

    action = ChipAction(kind=ChipActionKind.raise_ticket, payload={"client_id": "EVIL", "query_type": "ledger"})
    resp = orch.handle_turn(turn_request(thread_id, action=action))

    assert llm.calls == []
    assert ticketing.raised[0].client_id == "X008593"  # session, never the payload
    assert ticketing.raised[0].client_id != "EVIL"
    assert any(b.type == "ticket_confirmation" and b.ticket_id == "T-901" for b in resp.blocks)


def test_send_text_chip_routes_to_the_loop_not_dispatch():
    # send_text/deep_link chips carry a prefilled prompt and go through the loop.
    from app.contracts.router import RouterResult
    from tests.orchestrator.fakes import FakeRouter, end_turn_response, route_block, tool_use_response

    llm = FakeLLM([tool_use_response(route_block({"intent": "rag_qa"})), end_turn_response("hi")])
    orch, _ = make_orchestrator(llm=llm, router=FakeRouter(RouterResult(intent=Intent.rag_qa)))
    thread_id = bootstrap(orch)

    action = ChipAction(kind=ChipActionKind.send_text, payload={"text": "Show my ledger"})
    orch.handle_turn(turn_request(thread_id, action=action))
    assert llm.calls, "send_text must run the agentic loop"
