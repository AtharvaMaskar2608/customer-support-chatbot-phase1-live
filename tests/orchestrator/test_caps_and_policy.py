"""Caps + policy: 10-message soft close, ≤2-follow-up escalation, sticky-language."""

from __future__ import annotations

from app.contracts.router import ExtractedParams, Intent, Language, RouterResult
from app.contracts.wire import ConversationState
from tests.orchestrator.conftest import bootstrap, make_orchestrator, turn_request
from tests.orchestrator.fakes import (
    FakeLLM,
    FakeRouter,
    end_turn_response,
    route_block,
    tool_use_response,
)


def _escalation_labels(resp):
    return [c.label for row in resp.blocks if row.type == "chip_row" for c in row.chips]


def test_message_cap_soft_closes_past_ten_without_calling_llm():
    llm = FakeLLM()  # raises if the loop is entered — soft close must short-circuit
    orch, store = make_orchestrator(llm=llm)
    thread_id = bootstrap(orch)
    state = orch.sessions.get(thread_id)
    state.messages_used = 10  # ten turns already used
    state.turn_number = 10  # counters advance together — a real 10-turn thread has both at 10

    resp = orch.handle_turn(turn_request(thread_id, message="one more"))

    assert resp.caps.messages_used == 11
    assert resp.conversation_state is ConversationState.escalated
    assert "🎫 Raise a ticket" in _escalation_labels(resp)
    assert "📞 Call support" in _escalation_labels(resp)
    assert llm.calls == []  # short-circuited, no Claude call
    assert store.records[-1].turn_number == 11  # the soft-close turn is still recorded


def test_tenth_message_is_answered_not_soft_closed():
    llm = FakeLLM([tool_use_response(route_block({"intent": "rag_qa"})), end_turn_response("ok")])
    orch, _ = make_orchestrator(llm=llm, router=FakeRouter(RouterResult(intent=Intent.rag_qa)))
    thread_id = bootstrap(orch)
    state = orch.sessions.get(thread_id)
    state.messages_used = 9  # this incoming turn becomes the 10th

    resp = orch.handle_turn(turn_request(thread_id, message="tenth"))
    assert resp.caps.messages_used == 10
    assert resp.conversation_state is not ConversationState.escalated
    assert llm.calls, "the tenth message is answered normally"


def test_third_unresolved_disambiguation_escalates():
    router = FakeRouter(
        RouterResult(intent=Intent.report_pnl, follow_up_question="P&L or Tax P&L?")
    )
    llm = FakeLLM([tool_use_response(route_block({"intent": "report_pnl"}))])  # repeats each turn
    orch, _ = make_orchestrator(llm=llm, router=router)
    thread_id = bootstrap(orch)

    r1 = orch.handle_turn(turn_request(thread_id, message="reports"))
    assert r1.caps.follow_ups_used == 1
    assert r1.conversation_state is not ConversationState.escalated

    r2 = orch.handle_turn(turn_request(thread_id, message="still vague"))
    assert r2.caps.follow_ups_used == 2
    assert r2.conversation_state is not ConversationState.escalated

    r3 = orch.handle_turn(turn_request(thread_id, message="still vague again"))
    assert r3.conversation_state is ConversationState.escalated
    assert "🎫 Raise a ticket" in _escalation_labels(r3)
    assert r3.caps.follow_ups_used == 2  # not incremented past the cap


def test_sticky_language_locks_to_english_and_never_reopens():
    # Turn 1 resolves to English -> the thread locks English.
    english_router = FakeRouter(RouterResult(intent=Intent.rag_qa, detected_language=Language.english))
    llm = FakeLLM([tool_use_response(route_block({"intent": "rag_qa"})), end_turn_response("ok")])
    orch, _ = make_orchestrator(llm=llm, router=english_router)
    thread_id = bootstrap(orch)

    orch.handle_turn(turn_request(thread_id, message="hello there"))
    state = orch.sessions.get(thread_id)
    assert state.detected_language is Language.english
    assert state.language_locked is True

    # Turn 2 "detects" Hindi, but English is terminal — the lock must hold.
    orch.services.router = FakeRouter(RouterResult(intent=Intent.rag_qa, detected_language=Language.hindi))
    orch.handle_turn(turn_request(thread_id, message="फिर से"))
    state = orch.sessions.get(thread_id)
    assert state.detected_language is Language.english
    assert state.language_locked is True
