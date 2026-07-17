"""Service wiring tests (proposal §Contracts & API structure — respond / retrieve /
answer / search_kb).

FakeRetriever + FakeLLMClient — no DB, no network. Asserts the public surface the
proposal promises: ``respond`` retrieves then answers, attaches the REAL
``retrieval_context`` (canonical ``list[str]``), and threads the sticky-language
decision from ``ConversationContext`` into generation; ``search_kb`` is the tool
body running retrieval; ``tool_result_text`` formats the fused chunks for the
agent loop.
"""

from __future__ import annotations

import json

import pytest

from app.config.db import make_engine
from app.contracts.router import ConversationContext, Language
from app.rag.models import RefusalReason, RetrievedChunk
from app.rag.service import RagService, tool_result_text
from tests.rag.conftest import FakeLLMClient, FakeRetriever


def _chunk(cid: str, text: str = "fact") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid,
        text=text,
        source_id=f"S:{cid}",
        vector_score=0.9,
        fts_rank=0.1,
        fused_score=0.5,
    )


def _completion(**fields) -> str:
    payload = {"answer": "", "citations": [], "refused": False, "refusal_reason": None}
    payload.update(fields)
    return json.dumps(payload)


def _ctx(**over) -> ConversationContext:
    base = dict(
        user_id="u1", session_id="s1", access_token="tok", platform="android", page="home"
    )
    base.update(over)
    return ConversationContext(**base)


def _service(chunks, completion) -> RagService:
    # The bogus-DSN engine is never touched: FakeRetriever replaces the retriever,
    # and generation goes through the injected FakeLLMClient.
    svc = RagService(
        make_engine("postgresql://u:p@localhost/db"),
        llm=FakeLLMClient(completion),
    )
    svc.retriever = FakeRetriever(chunks)
    return svc


@pytest.mark.asyncio
async def test_respond_retrieves_then_answers_and_attaches_real_context():
    chunks = [_chunk("7", "To check SIPs open the tab."), _chunk("8", "second fact")]
    svc = _service(chunks, _completion(answer="Open the SIP tab.", citations=["7"]))

    result = await svc.respond("how do I check my SIPs", _ctx())

    assert result.answer == "Open the SIP tab."
    assert result.citations == ["7"]
    # the REAL retrieved set, canonical list[str] — for store / tracing / DeepEval
    assert result.retrieval_context == ["To check SIPs open the tab.", "second fact"]
    assert svc.retriever.calls[0][0] == "how do I check my SIPs"


@pytest.mark.asyncio
async def test_respond_threads_sticky_language_into_generation():
    svc = _service([_chunk("7")], _completion(answer="जवाब", citations=["7"]))

    await svc.respond("q", _ctx(detected_language=Language.hindi))

    # the sticky-language decision reached the generator's system prompt
    assert "Hindi" in svc.generator.llm.requests[0]["system"]


@pytest.mark.asyncio
async def test_respond_no_match_refuses_without_llm_call():
    # FakeRetriever returns nothing → D4 refusal, no generation call.
    svc = _service([], _completion(answer="unused"))

    result = await svc.respond("obscure question", _ctx())

    assert result.refused is True
    assert result.refusal_reason is RefusalReason.no_relevant_context
    assert svc.generator.llm.requests == []


@pytest.mark.asyncio
async def test_search_kb_runs_retrieval_and_returns_fused_chunks():
    chunks = [_chunk("7"), _chunk("8")]
    svc = _service(chunks, _completion())

    out = await svc.search_kb("nominee")

    assert [c.chunk_id for c in out] == ["7", "8"]
    assert svc.retriever.calls[0][0] == "nominee"


@pytest.mark.asyncio
async def test_answer_generates_over_explicit_context():
    svc = _service([], _completion(answer="grounded", citations=["7"]))

    result = svc.answer("q", [_chunk("7")], Language.english)

    assert result.answer == "grounded"
    assert result.citations == ["7"]


def test_tool_result_text_formats_chunks_for_the_agent_loop():
    text = tool_result_text([_chunk("7", "alpha"), _chunk("8", "beta")])
    assert "[id: 7]" in text and "alpha" in text
    assert "[id: 8]" in text and "beta" in text


def test_tool_result_text_empty_is_explicit_no_match():
    assert tool_result_text([]) == "No knowledge-base entries matched."
