"""Native tool-use agentic loop mechanics (done condition).

Asserts: free-text turns run the loop; a faked tool_use → tool_result → follow-up
cycle matches tool_use_id on the appended tool_result; the fulfilment output comes
from the TOOL result (not Claude prose); a parallel tool_use fixture returns both
results in ONE user message; a failed tool execution returns is_error: true rather
than being dropped; ≤3 tool iterations are enforced then escalation; refusal maps to
the escalation chips; pause_turn is re-sent.
"""

from __future__ import annotations

from app.contracts.rag import RagAnswer
from app.contracts.router import ExtractedParams, Intent, RouterResult
from app.contracts.wire import FileCard
from app.orchestrator.ports import StepResult
from tests.orchestrator.conftest import bootstrap, make_orchestrator, turn_request
from tests.orchestrator.fakes import (
    FailingEngine,
    FakeEngine,
    FakeLLM,
    FakeRag,
    FakeRouter,
    FakeToolUse,
    end_turn_response,
    pause_turn_response,
    refusal_response,
    route_block,
    tool_use_response,
)


def _pnl_router() -> FakeRouter:
    return FakeRouter(RouterResult(intent=Intent.report_pnl, extracted_params=ExtractedParams()))


def test_freetext_runs_loop_and_fulfilment_comes_from_tool_result():
    # Script: forced route -> route tool_use; then get_pnl_report tool_use; then end_turn.
    llm = FakeLLM(
        [
            tool_use_response(route_block({"intent": "report_pnl"}, id="tu_route")),
            tool_use_response(FakeToolUse(id="tu_pnl", name="get_pnl_report", input={})),
            end_turn_response("Here's your P&L."),
        ]
    )
    engine = FakeEngine(StepResult(blocks=[FileCard(filename="P&L_Statement.pdf", size_label="182 KB", format="pdf")]))
    orch, store = make_orchestrator(llm=llm, router=_pnl_router(), engine=engine)
    thread_id = bootstrap(orch)

    resp = orch.handle_turn(turn_request(thread_id, message="get my p&l"))

    # The FileCard came from the engine tool result, never from Claude's closing prose.
    file_cards = [b for b in resp.blocks if b.type == "file_card"]
    assert len(file_cards) == 1
    assert file_cards[0].filename == "P&L_Statement.pdf"
    assert resp.intent is Intent.report_pnl
    assert engine.calls, "engine.step must be the fulfilment source"

    # The enqueued record proves tool_use_id was matched on the appended tool_result.
    record = store.records[-1]
    names = [tc["name"] for tc in record.tool_calls]
    assert names == ["route", "get_pnl_report"]


def test_tool_result_matches_tool_use_id_in_transcript():
    llm = FakeLLM(
        [
            tool_use_response(route_block({"intent": "report_pnl"}, id="tu_route_x")),
            tool_use_response(FakeToolUse(id="tu_pnl_y", name="get_pnl_report", input={})),
            end_turn_response(),
        ]
    )
    orch, _ = make_orchestrator(llm=llm, router=_pnl_router())
    thread_id = bootstrap(orch)
    orch.handle_turn(turn_request(thread_id, message="p&l please"))

    state = orch.sessions.get(thread_id)
    tool_result_ids = [
        block["tool_use_id"]
        for msg in state.messages
        if msg["role"] == "user" and isinstance(msg["content"], list)
        for block in msg["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert "tu_route_x" in tool_result_ids
    assert "tu_pnl_y" in tool_result_ids


def test_parallel_tool_use_returns_both_results_in_one_user_message():
    # One assistant message with TWO tool_use blocks -> both results in ONE user turn.
    llm = FakeLLM(
        [
            tool_use_response(route_block({"intent": "report_cml"}, id="tu_route")),
            tool_use_response(
                FakeToolUse(id="tu_cml", name="get_cml", input={}),
                FakeToolUse(id="tu_kb", name="search_kb", input={"query": "how do I open it?"}),
            ),
            end_turn_response(),
        ]
    )
    engine = FakeEngine(StepResult(blocks=[FileCard(filename="Client_Master_List.pdf", size_label="20 KB", format="pdf")]))
    rag = FakeRag(RagAnswer(answer="Open it with your PAN.", retrieval_context=["kb-1"]))
    orch, _ = make_orchestrator(
        llm=llm, router=FakeRouter(RouterResult(intent=Intent.report_cml)), engine=engine, rag=rag
    )
    thread_id = bootstrap(orch)
    orch.handle_turn(turn_request(thread_id, message="get my cml and tell me how to open it"))

    state = orch.sessions.get(thread_id)
    # Find the user message carrying the parallel results.
    parallel = [
        msg
        for msg in state.messages
        if msg["role"] == "user"
        and isinstance(msg["content"], list)
        and {b["tool_use_id"] for b in msg["content"] if isinstance(b, dict)} == {"tu_cml", "tu_kb"}
    ]
    assert len(parallel) == 1, "both parallel tool_results must be in a single user message"
    assert all(b["type"] == "tool_result" for b in parallel[0]["content"])


def test_failed_tool_execution_returns_is_error_not_dropped():
    llm = FakeLLM(
        [
            tool_use_response(route_block({"intent": "report_pnl"}, id="tu_route")),
            tool_use_response(FakeToolUse(id="tu_pnl", name="get_pnl_report", input={})),
            end_turn_response("Sorry, that failed."),
        ]
    )
    orch, store = make_orchestrator(llm=llm, router=_pnl_router(), engine=FailingEngine())
    thread_id = bootstrap(orch)
    orch.handle_turn(turn_request(thread_id, message="p&l"))

    state = orch.sessions.get(thread_id)
    err_results = [
        b
        for msg in state.messages
        if msg["role"] == "user" and isinstance(msg["content"], list)
        for b in msg["content"]
        if isinstance(b, dict) and b.get("tool_use_id") == "tu_pnl"
    ]
    assert len(err_results) == 1
    assert err_results[0]["is_error"] is True  # surfaced, never dropped
    # And it is recorded as an errored tool call.
    pnl_calls = [tc for tc in store.records[-1].tool_calls if tc["name"] == "get_pnl_report"]
    assert pnl_calls and pnl_calls[0]["is_error"] is True


def test_iteration_cap_escalates_after_three_tool_iterations():
    # An "always tool_use" script must escalate to the ticket/call chips after 3 rounds.
    llm = FakeLLM(
        [
            tool_use_response(route_block({"intent": "report_pnl"}, id="r")),
            tool_use_response(FakeToolUse(id="a", name="get_pnl_report", input={})),
            tool_use_response(FakeToolUse(id="b", name="get_pnl_report", input={})),
            tool_use_response(FakeToolUse(id="c", name="get_pnl_report", input={})),
            tool_use_response(FakeToolUse(id="d", name="get_pnl_report", input={})),
        ]
    )
    orch, store = make_orchestrator(llm=llm, router=_pnl_router())
    thread_id = bootstrap(orch)
    resp = orch.handle_turn(turn_request(thread_id, message="loop forever"))

    # Exactly three tool iterations executed, then escalation.
    assert len(store.records[-1].tool_calls) == 3
    from app.contracts.wire import ConversationState

    assert resp.conversation_state is ConversationState.escalated
    chip_labels = [c.label for row in resp.blocks if row.type == "chip_row" for c in row.chips]
    assert "🎫 Raise a ticket" in chip_labels
    assert "📞 Call support" in chip_labels


def test_refusal_maps_to_escalation_chips():
    llm = FakeLLM([tool_use_response(route_block()), refusal_response()])
    orch, _ = make_orchestrator(llm=llm, router=FakeRouter(RouterResult(intent=Intent.rag_qa)))
    thread_id = bootstrap(orch)
    resp = orch.handle_turn(turn_request(thread_id, message="do something disallowed"))

    from app.contracts.wire import ConversationState

    assert resp.conversation_state is ConversationState.escalated
    chip_labels = [c.label for row in resp.blocks if row.type == "chip_row" for c in row.chips]
    assert "🎫 Raise a ticket" in chip_labels


def test_pause_turn_is_resent_then_continues():
    llm = FakeLLM(
        [
            tool_use_response(route_block({"intent": "rag_qa"}, id="tu_route")),
            pause_turn_response(),
            tool_use_response(FakeToolUse(id="tu_kb", name="search_kb", input={"query": "q"})),
            end_turn_response("Answered."),
        ]
    )
    rag = FakeRag(RagAnswer(answer="Grounded answer.", retrieval_context=["kb-9"]))
    orch, store = make_orchestrator(llm=llm, router=FakeRouter(RouterResult(intent=Intent.rag_qa)), rag=rag)
    thread_id = bootstrap(orch)
    resp = orch.handle_turn(turn_request(thread_id, message="a how-to"))

    # The rag answer (from the tool) survived the pause_turn re-send.
    assert any(b.type == "bubble" and "Grounded answer." in b.text for b in resp.blocks)
    assert store.records[-1].retrieval_context == ["kb-9"]
