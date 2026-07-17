"""RAG contract-type tests (specs/router-contract §RAG answer and retrieved-chunk).

Asserts RetrievedChunk fields, RagAnswer citations + refusal flag, and the
canonical retrieval_context: list[str] shape.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.rag import (
    RagAnswer,
    RefusalReason,
    RetrievalContext,
    RetrievedChunk,
)


def test_retrieved_chunk_fields():
    c = RetrievedChunk(
        chunk_id="c1",
        text="How to check trade details...",
        source_id="kb-entry-42",
        vector_score=0.81,
        fts_rank=3.0,
        fused_score=0.65,
    )
    assert c.chunk_id == "c1"
    assert c.source_id == "kb-entry-42"
    assert c.vector_score == 0.81 and c.fts_rank == 3.0 and c.fused_score == 0.65
    # frozen contract value object.
    with pytest.raises(ValidationError):
        c.text = "mutated"


def test_rag_answer_citations_and_refusal():
    a = RagAnswer(
        answer="You can view trade details under Reports.",
        citations=["c1", "c2"],
        retrieval_context=["chunk one text", "chunk two text"],
    )
    assert a.citations == ["c1", "c2"]
    assert a.refused is False and a.refusal_reason is None
    # retrieval_context is the canonical list[str].
    assert a.retrieval_context == ["chunk one text", "chunk two text"]
    assert all(isinstance(x, str) for x in a.retrieval_context)

    refused = RagAnswer(
        answer="",
        refused=True,
        refusal_reason=RefusalReason.investment_advice,
    )
    assert refused.refused is True
    assert refused.refusal_reason is RefusalReason.investment_advice


def test_retrieval_context_is_list_of_str_alias():
    # The canonical alias is exactly list[str].
    assert RetrievalContext == list[str]
