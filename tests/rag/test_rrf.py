"""RRF fusion unit tests (proposal §What Changes — RRF fusion).

Exercises the exact ``score = Σ 1/(rrf_k + rank)`` math and the both-lists boost
deterministically, with no DB — the retriever's ``_rrf_fuse`` over synthetic
rank lists. (The real SQL is exercised separately against pgvector.)
"""

from __future__ import annotations

import pytest

from app.config.db import make_engine
from app.rag.config import RagConfig
from app.rag.retriever import Retriever

RRF_K = 60


def _retriever() -> Retriever:
    # db + embedder are unused by _rrf_fuse; pass inert placeholders.
    return Retriever(make_engine("postgresql://u:p@localhost/db"), embedder=None, config=RagConfig())


# rows are (id, source_sheet, source_row, chunk, score), pre-ordered by rank.
_VECTOR = [
    (7, "MF", 7, "chunk7", 0.99),
    (8, "MF", 8, "chunk8", 0.80),
    (11, "MF", 11, "chunk11", 0.70),
]
_FTS = [
    (223, "Nom", 223, "chunk223", 0.05),
    (7, "MF", 7, "chunk7", 0.03),   # id 7 also here -> both-lists
    (224, "Nom", 224, "chunk224", 0.02),
]


def test_rrf_exact_scores_and_both_list_boost():
    fused = _retriever()._rrf_fuse(_VECTOR, _FTS)
    by_id = {h.chunk_id: h for h in fused}

    # union of both lists, nothing dropped
    assert set(by_id) == {"7", "8", "11", "223", "224"}

    # id 7: vector rank1 + fts rank2
    assert by_id["7"].fused_score == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 2))
    assert by_id["7"].vector_score == 0.99 and by_id["7"].fts_rank == 0.03
    assert by_id["7"].source_id == "MF:7"

    # single-list members
    assert by_id["223"].fused_score == pytest.approx(1 / (RRF_K + 1))
    assert by_id["223"].vector_score == 0.0  # fts-only
    assert by_id["8"].fused_score == pytest.approx(1 / (RRF_K + 2))
    assert by_id["8"].fts_rank == 0.0  # vector-only

    # the both-lists doc outranks every single-list doc
    single_max = max(by_id[i].fused_score for i in ("8", "11", "223", "224"))
    assert by_id["7"].fused_score > single_max


def test_rrf_ordering_is_deterministic():
    fused = _retriever()._rrf_fuse(_VECTOR, _FTS)
    order = [h.chunk_id for h in fused]
    # 7 (both) first; 223 (fts r1) > 8 (vec r2); 11 & 224 tie on score, vector_score breaks it (11 has 0.70 > 0)
    assert order == ["7", "223", "8", "11", "224"]


def test_rrf_top_of_each_list_present():
    # a purely disjoint pair of lists still fuses to their union
    fused = _retriever()._rrf_fuse(
        [(1, "A", 1, "a", 0.9)], [(2, "B", 2, "b", 0.5)]
    )
    assert {h.chunk_id for h in fused} == {"1", "2"}
    assert all(h.fused_score == pytest.approx(1 / (RRF_K + 1)) for h in fused)


def test_rrf_empty_lists():
    assert _retriever()._rrf_fuse([], []) == []
    only_vec = _retriever()._rrf_fuse([(5, "A", 5, "x", 0.4)], [])
    assert [h.chunk_id for h in only_vec] == ["5"]
    assert only_vec[0].fts_rank == 0.0
