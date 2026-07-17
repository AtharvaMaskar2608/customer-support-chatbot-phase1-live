"""Fan-out + security: store.enqueue and the tracing root agent span are invoked
without the response awaiting the DB write; client_id is taken from the session,
never the request body."""

from __future__ import annotations

from app.contracts.router import Intent, RouterResult
from app.contracts.tracing import SpanType, trace_manager
from app.contracts.wire import FileCard
from app.orchestrator.ports import StepResult
from tests.orchestrator.conftest import bootstrap, make_orchestrator, turn_request
from tests.orchestrator.fakes import (
    FakeEngine,
    FakeLLM,
    FakeRouter,
    FakeTicketing,
    FakeToolUse,
    end_turn_response,
    route_block,
    tool_use_response,
)


def test_turn_enqueues_a_turn_record_with_the_turn_payload():
    llm = FakeLLM(
        [
            tool_use_response(route_block({"intent": "report_pnl"})),
            tool_use_response(FakeToolUse(id="tu_pnl", name="get_pnl_report", input={})),
            end_turn_response("Here you go."),
        ]
    )
    engine = FakeEngine(StepResult(blocks=[FileCard(filename="P&L.pdf", size_label="1 KB", format="pdf")]))
    orch, store = make_orchestrator(llm=llm, router=FakeRouter(RouterResult(intent=Intent.report_pnl)), engine=engine)
    thread_id = bootstrap(orch)

    resp = orch.handle_turn(turn_request(thread_id, message="p&l"))

    assert len(store.records) == 1  # the response did not wait on a DB layer — enqueue is fire-and-forget
    record = store.records[0]
    assert record.thread_id == thread_id
    assert record.user_id == "X008593"
    assert record.turn_number == resp.turn_number == 1
    assert record.intent is Intent.report_pnl
    assert record.user_message == "p&l"
    assert record.render_blocks  # the assembled blocks are captured for persistence
    assert record.model_version  # provenance stitched on


def test_tracing_root_agent_span_wraps_the_turn():
    llm = FakeLLM([tool_use_response(route_block({"intent": "rag_qa"})), end_turn_response()])
    orch, _ = make_orchestrator(llm=llm, router=FakeRouter(RouterResult(intent=Intent.rag_qa)))
    thread_id = bootstrap(orch)

    orch.handle_turn(turn_request(thread_id, message="hello"))

    span = trace_manager.last_span
    assert span is not None
    assert span.span_type is SpanType.agent
    assert span.attributes.get("thread_id") == thread_id
    assert span.attributes.get("user_id") == "X008593"
    assert span.attributes.get("turn_number") == 1


def test_raise_ticket_tool_binds_client_id_from_session_not_model_args():
    llm = FakeLLM(
        [
            tool_use_response(route_block({"intent": "raise_ticket"})),
            tool_use_response(
                FakeToolUse(
                    id="tu_ticket",
                    name="raise_ticket",
                    # The model supplies an attacker-controlled client_id — it MUST be ignored.
                    input={"client_id": "X999999", "query_type": "ledger", "transcript_ref": "ref"},
                )
            ),
            end_turn_response("Raised."),
        ]
    )
    ticketing = FakeTicketing(ticket_id="T-500")
    orch, _ = make_orchestrator(llm=llm, router=FakeRouter(RouterResult(intent=Intent.raise_ticket)), ticketing=ticketing)
    thread_id = bootstrap(orch)

    resp = orch.handle_turn(turn_request(thread_id, message="raise a ticket for my ledger"))

    assert ticketing.raised[0].client_id == "X008593"  # from the session claim
    assert ticketing.raised[0].client_id != "X999999"  # never the model/request body
    assert any(b.type == "ticket_confirmation" and b.ticket_id == "T-500" for b in resp.blocks)


def test_secrets_never_reach_the_serialized_response():
    llm = FakeLLM([tool_use_response(route_block({"intent": "rag_qa"})), end_turn_response("ok")])
    orch, _ = make_orchestrator(llm=llm, router=FakeRouter(RouterResult(intent=Intent.rag_qa)))
    thread_id = bootstrap(orch)
    resp = orch.handle_turn(turn_request(thread_id, message="hi"))
    blob = resp.model_dump_json(by_alias=True)
    assert "s-secret" not in blob
    assert "jwt-secret" not in blob
