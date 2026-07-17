"""Hybrid retrieval against real pgvector (proposal §Done condition, §What Changes).

Exercises the actual vector ``<=>`` scan + inline FTS + RRF fusion against an
ephemeral ``pgvector/pgvector:pg16`` container seeded from the committed fixture.
Query vectors come from a FakeEmbedder seeded with a real stored embedding, so
vector ranking is deterministic (self-match at rank 1) without any network.
Skips cleanly when Docker/the image is unavailable.
"""

from __future__ import annotations

import pytest

from app.rag.config import RagConfig
from app.rag.retriever import Retriever
from tests.rag.conftest import FakeEmbedder, seed_embedding

# A row whose stored embedding is the query vector → deterministic vector rank 1.
_SIP_ROW = 7
# Distinctive FTS keyword absent from the SIP rows' chunks.
_FTS_QUERY = "nominee"
_NOMINEE_IDS = {"223", "224", "225"}


@pytest.mark.asyncio
async def test_vector_self_match_ranks_first(pgvector_db, seed_rows):
    embedder = FakeEmbedder(seed_embedding(seed_rows, _SIP_ROW))
    retriever = Retriever(pgvector_db, embedder, RagConfig())
    results = await retriever.retrieve("how do I check the count of my SIPs")

    assert results, "expected retrieved chunks"
    assert results[0].chunk_id == str(_SIP_ROW)
    # exact cosine self-match ~ 1.0
    assert results[0].vector_score > 0.999
    assert results[0].fused_score > 0
    assert results[0].source_id == "Mutual Fund:7"
    assert "SIP" in results[0].text


@pytest.mark.asyncio
async def test_hybrid_fuses_both_retrievers(pgvector_db, seed_rows):
    # Small candidate depth so the vector list (SIP neighbours) stays disjoint
    # from the FTS list (nominee rows) — proving BOTH retrievers contribute.
    embedder = FakeEmbedder(seed_embedding(seed_rows, _SIP_ROW))
    retriever = Retriever(pgvector_db, embedder, RagConfig(candidate_k=3, context_k=6))
    results = await retriever.retrieve(_FTS_QUERY)

    ids = {c.chunk_id for c in results}
    by_id = {c.chunk_id: c for c in results}

    # vector-side contributor: the SIP row, present with no FTS match on "nominee"
    assert str(_SIP_ROW) in ids
    assert by_id[str(_SIP_ROW)].fts_rank == 0.0
    assert by_id[str(_SIP_ROW)].vector_score > 0.0

    # FTS-side contributor: a nominee row, present with no vector match (candidate_k=3)
    fts_only = _NOMINEE_IDS & ids
    assert fts_only, "expected an FTS-only nominee row in the fused set"
    for cid in fts_only:
        assert by_id[cid].fts_rank > 0.0
        assert by_id[cid].vector_score == 0.0


@pytest.mark.asyncio
async def test_fts_keyword_matches(pgvector_db, seed_rows):
    embedder = FakeEmbedder(seed_embedding(seed_rows, _SIP_ROW))
    retriever = Retriever(pgvector_db, embedder, RagConfig(candidate_k=3, context_k=10))
    results = await retriever.retrieve(_FTS_QUERY)
    # at least one nominee row surfaced by FTS with a positive rank
    assert any(c.chunk_id in _NOMINEE_IDS and c.fts_rank > 0.0 for c in results)


@pytest.mark.asyncio
async def test_context_k_limits_result_size(pgvector_db, seed_rows):
    embedder = FakeEmbedder(seed_embedding(seed_rows, _SIP_ROW))
    retriever = Retriever(pgvector_db, embedder, RagConfig())
    assert len(await retriever.retrieve("SIP", k=3)) == 3
    assert len(await retriever.retrieve("SIP")) == RagConfig().context_k  # default 5


@pytest.mark.asyncio
async def test_retrieved_chunk_shape(pgvector_db, seed_rows):
    embedder = FakeEmbedder(seed_embedding(seed_rows, _SIP_ROW))
    retriever = Retriever(pgvector_db, embedder, RagConfig())
    for chunk in await retriever.retrieve("SIP"):
        assert isinstance(chunk.chunk_id, str)
        assert ":" in chunk.source_id
        assert chunk.text
        assert isinstance(chunk.vector_score, float)
        assert isinstance(chunk.fts_rank, float)
        assert isinstance(chunk.fused_score, float)
