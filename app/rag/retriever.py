"""Hybrid retriever: vector + FTS + RRF over ``qa_chunks`` (spec §5).

Three stages, each owned here:

* **Vector search** — exact cosine (``vector_cosine_ops`` / ``<=>``) sequential
  scan over ``qa_chunks.embedding``, top ``candidate_k``. 3072-dim exceeds
  pgvector's 2000-dim ANN cap, so the sequential scan is the correct, confirmed
  choice at 1,102 rows. ``vector_score = 1 - cosine_distance`` (higher = closer).
* **FTS search** — Postgres full-text over the ``chunk`` column computed inline
  (``to_tsvector('english', chunk) @@ websearch_to_tsquery('english', :q)``,
  ranked by ``ts_rank_cd``), top ``candidate_k``. Semantically identical to the
  KB's stored generated ``fts`` column (``chunk`` is NOT NULL, same regconfig).
* **RRF fusion** — combine the two rank lists with Reciprocal Rank Fusion
  (``score = Σ 1/(rrf_k + rank)``) and return the top ``context_k`` fused chunks.

The query vector is passed as a ``pgvector.Vector`` (numpy is not a dependency).
DB failures surface as ``RagError(stage="db")``; the retrieval set (masked) and
counters are recorded on a ``retriever`` tracing span.
"""

from __future__ import annotations

from typing import Any

from pgvector import Vector

from app.config.db import Database
from app.contracts.tracing import MaskFn, SpanType, default_mask, trace_manager
from app.rag.config import RagConfig
from app.rag.embeddings import QueryEmbedder
from app.rag.models import RagError, RetrievedChunk

# Exact cosine sequential scan, top candidate_k. vector_score = 1 - distance.
_VECTOR_SQL = """
SELECT id, source_sheet, source_row, chunk,
       1 - (embedding <=> %(qvec)s) AS vector_score
FROM qa_chunks
WHERE embedding IS NOT NULL
ORDER BY embedding <=> %(qvec)s
LIMIT %(k)s
"""

# Inline FTS (no dependency on the stored generated column), ranked by ts_rank_cd.
_FTS_SQL = """
SELECT id, source_sheet, source_row, chunk,
       ts_rank_cd(to_tsvector('english', chunk),
                  websearch_to_tsquery('english', %(q)s)) AS fts_rank
FROM qa_chunks
WHERE to_tsvector('english', chunk) @@ websearch_to_tsquery('english', %(q)s)
ORDER BY fts_rank DESC, id ASC
LIMIT %(k)s
"""


class _Hit:
    """Mutable accumulator for one candidate across the two rank lists."""

    __slots__ = (
        "chunk_id",
        "text",
        "source_id",
        "vector_score",
        "fts_rank",
        "fused_score",
    )

    def __init__(self, chunk_id: str, text: str, source_id: str) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.source_id = source_id
        self.vector_score = 0.0
        self.fts_rank = 0.0
        self.fused_score = 0.0


def _source_id(source_sheet: Any, source_row: Any) -> str:
    """KB-entry provenance id from the source spreadsheet coordinates."""
    return f"{source_sheet}:{source_row}"


class Retriever:
    """Hybrid retriever over the shared async ``Database``."""

    def __init__(
        self,
        db: Database,
        embedder: QueryEmbedder,
        config: RagConfig | None = None,
        *,
        mask: MaskFn = default_mask,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.config = config or RagConfig()
        self.mask = mask

    async def retrieve(self, query: str, k: int | None = None) -> list[RetrievedChunk]:
        """Embed ``query``, run vector + FTS search (each top ``candidate_k``),
        RRF-fuse, and return the top ``k`` (default ``context_k``) fused chunks."""
        context_k = self.config.context_k if k is None else k
        query_vector = self.embedder.embed(query)  # RagError(embedding) on failure

        with trace_manager.span(SpanType.retriever) as span:
            try:
                async with self.db.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            _VECTOR_SQL,
                            {"qvec": Vector(query_vector), "k": self.config.candidate_k},
                        )
                        vector_rows = await cur.fetchall()
                        await cur.execute(
                            _FTS_SQL,
                            {"q": query, "k": self.config.candidate_k},
                        )
                        fts_rows = await cur.fetchall()
            except RagError:
                raise
            except Exception as exc:  # noqa: BLE001 — normalize DB failures
                raise RagError("qa_chunks retrieval failed", stage="db", cause=exc) from exc

            fused = self._rrf_fuse(vector_rows, fts_rows)[:context_k]
            span.set(
                candidate_k=self.config.candidate_k,
                context_k=context_k,
                vector_hits=len(vector_rows),
                fts_hits=len(fts_rows),
                retrieval_context=self.mask([hit.text for hit in fused]),
            )
        return [
            RetrievedChunk(
                chunk_id=hit.chunk_id,
                text=hit.text,
                source_id=hit.source_id,
                vector_score=hit.vector_score,
                fts_rank=hit.fts_rank,
                fused_score=hit.fused_score,
            )
            for hit in fused
        ]

    def _rrf_fuse(
        self, vector_rows: list[tuple], fts_rows: list[tuple]
    ) -> list[_Hit]:
        """Reciprocal Rank Fusion of the two rank lists.

        ``fused_score = Σ 1/(rrf_k + rank)`` over the lists a chunk appears in
        (rank is 1-based within each list). Ordered by fused score desc, with a
        deterministic tie-break (vector score desc, then chunk id).
        """
        rrf_k = self.config.rrf_k
        hits: dict[str, _Hit] = {}

        def _get(row: tuple) -> _Hit:
            chunk_id = str(row[0])
            hit = hits.get(chunk_id)
            if hit is None:
                hit = _Hit(chunk_id, row[3], _source_id(row[1], row[2]))
                hits[chunk_id] = hit
            return hit

        for rank, row in enumerate(vector_rows, start=1):
            hit = _get(row)
            hit.vector_score = float(row[4])
            hit.fused_score += 1.0 / (rrf_k + rank)

        for rank, row in enumerate(fts_rows, start=1):
            hit = _get(row)
            hit.fts_rank = float(row[4])
            hit.fused_score += 1.0 / (rrf_k + rank)

        return sorted(
            hits.values(),
            key=lambda h: (-h.fused_score, -h.vector_score, h.chunk_id),
        )


__all__ = ["Retriever"]
