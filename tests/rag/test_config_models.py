"""Config + models tests (proposal §Proposed decisions, §Contracts).

RagConfig must mirror the frozen RagTunables (25/60/5/none); models must
re-export the frozen contract types (not redefine them) and add RagError.
"""

from __future__ import annotations

import pytest

from app.config.schema import RagTunables
from app.contracts.rag import RagAnswer as FrozenRagAnswer
from app.contracts.rag import RefusalReason as FrozenRefusalReason
from app.contracts.rag import RetrievalContext as FrozenRetrievalContext
from app.contracts.rag import RetrievedChunk as FrozenRetrievedChunk
from app.rag.config import (
    RAG_CANDIDATE_K,
    RAG_CONTEXT_K,
    RERANKER,
    RRF_K,
    RagConfig,
)
from app.rag.models import (
    RagAnswer,
    RagError,
    RefusalReason,
    RetrievalContext,
    RetrievedChunk,
)


def test_default_config_mirrors_frozen_tunables():
    cfg = RagConfig()
    assert (cfg.candidate_k, cfg.rrf_k, cfg.context_k, cfg.reranker) == (25, 60, 5, "none")
    # module constants agree
    assert (RAG_CANDIDATE_K, RRF_K, RAG_CONTEXT_K, RERANKER) == (25, 60, 5, "none")
    # and they mirror the frozen remote-config defaults
    t = RagTunables()
    assert (t.rag_candidate_k, t.rrf_k, t.rag_context_k, t.reranker) == (
        cfg.candidate_k,
        cfg.rrf_k,
        cfg.context_k,
        cfg.reranker,
    )


def test_config_from_tunables():
    t = RagTunables(rag_candidate_k=40, rrf_k=10, rag_context_k=3, reranker="cohere")
    cfg = RagConfig.from_tunables(t)
    assert (cfg.candidate_k, cfg.rrf_k, cfg.context_k, cfg.reranker) == (40, 10, 3, "cohere")


def test_models_reexport_frozen_types():
    # Re-exports must BE the frozen contract types, not lookalikes.
    assert RetrievedChunk is FrozenRetrievedChunk
    assert RagAnswer is FrozenRagAnswer
    assert RetrievalContext is FrozenRetrievalContext
    assert RefusalReason is FrozenRefusalReason
    assert RetrievalContext == list[str]


def test_rag_error_carries_stage():
    cause = ValueError("boom")
    err = RagError("embedding failed", stage="embedding", cause=cause)
    assert err.stage == "embedding"
    assert err.cause is cause
    assert isinstance(err, Exception)
    with pytest.raises(RagError):
        raise RagError("db down", stage="db")
