"""Session bootstrap (the first /api/chat turn) — done condition: time-correct
greeting + the correct entry surface's chips from remote-config; thread_id minted
once and echoed on every later turn."""

from __future__ import annotations

from datetime import datetime

from app.contracts.wire import ConversationState, EntrySurface
from app.orchestrator.bootstrap import build_config_slice, select_greeting
from app.config.defaults import DEFAULT_CONFIG
from tests.orchestrator.conftest import bootstrap, make_orchestrator, seed_request, turn_request
from tests.orchestrator.fakes import FakeLLM, end_turn_response, route_block, tool_use_response


def test_seed_returns_greeting_bubble_and_entry_chips():
    orch, store = make_orchestrator()
    resp = orch.handle_turn(seed_request(page="support"))

    assert [b.type for b in resp.blocks] == ["bubble", "chip_row"]
    assert resp.blocks[0].compliance_footer is True
    assert resp.blocks[0].text  # greeting present, {client_id} substituted
    assert "{client_id}" not in resp.blocks[0].text
    assert resp.conversation_state is ConversationState.greeting
    assert resp.config_slice is not None
    assert len(resp.config_slice.entry_chips) == 4
    assert resp.intent is None
    assert resp.caps.messages_cap == DEFAULT_CONFIG.limits.message_cap


def test_reports_page_selects_reports_chips():
    orch, _ = make_orchestrator()
    resp = orch.handle_turn(seed_request(page="reports"))
    labels = [c.label for c in resp.config_slice.entry_chips]
    assert "📁 Holding Statement" in labels


def test_seed_config_slice_excludes_server_only_config():
    orch, _ = make_orchestrator()
    resp = orch.handle_turn(seed_request())
    blob = resp.config_slice.model_dump_json()
    for forbidden in ("rag_candidate_k", "rrf_k", "reranker", "calendar_bounds"):
        assert forbidden not in blob


def test_greeting_is_time_aware_ist_buckets():
    pool = DEFAULT_CONFIG.greeting
    cid = "X008593"
    assert select_greeting(pool, cid, datetime(2026, 7, 17, 7, 30)) == pool.morning.replace("{client_id}", cid)
    assert select_greeting(pool, cid, datetime(2026, 7, 17, 10, 0)) == pool.market_hours.replace("{client_id}", cid)
    assert select_greeting(pool, cid, datetime(2026, 7, 17, 18, 0)) == pool.post_market.replace("{client_id}", cid)
    assert select_greeting(pool, cid, datetime(2026, 7, 17, 2, 0)) == pool.default.replace("{client_id}", cid)


def test_config_slice_greeting_uses_session_client_id():
    slice_ = build_config_slice(DEFAULT_CONFIG, EntrySurface.support, "X008593")
    assert "X008593" in slice_.greeting


def test_thread_id_minted_once_and_echoed_every_turn():
    llm = FakeLLM([tool_use_response(route_block()), end_turn_response()])
    orch, _ = make_orchestrator(llm=llm)
    thread_id = bootstrap(orch)
    assert thread_id  # minted on the seed

    resp = orch.handle_turn(turn_request(thread_id, message="hi"))
    assert resp.thread_id == thread_id  # echoed, not re-minted
    assert resp.turn_number == 1
    assert resp.config_slice is None  # only the seed carries the config slice
