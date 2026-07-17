"""RAG tunables (mirrors the frozen ``RagTunables`` remote-config slice).

The four §5.4 decisions this change proposed and that landed frozen in the
remote-config schema: candidate depth per retriever (25), the RRF constant (60),
the final context size (5), and the reranker slot (explicit skip, ``"none"``).
``RagConfig`` is the local, immutable value object the retriever reads;
``from_tunables`` adapts a live ``RagTunables`` (server-only remote config) onto
it so the keys stay in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.schema import RagTunables

#: Candidate depth per retriever — deep enough for RRF to have signal from both
#: lists, trivial cost at 1,102 rows.
RAG_CANDIDATE_K = 25

#: RRF constant (Cormack et al.) — robust default, avoids over-weighting rank-1.
RRF_K = 60

#: Final fused context size handed to generation.
RAG_CONTEXT_K = 5

#: Reranker slot — explicit skip in Phase 1 (RRF is the ranking mechanism).
RERANKER = "none"


@dataclass(frozen=True)
class RagConfig:
    """Immutable RAG retrieval config. Defaults mirror the frozen ``RagTunables``."""

    candidate_k: int = RAG_CANDIDATE_K
    rrf_k: int = RRF_K
    context_k: int = RAG_CONTEXT_K
    reranker: str = RERANKER

    @classmethod
    def from_tunables(cls, tunables: RagTunables) -> "RagConfig":
        """Build from the live remote-config ``RagTunables`` slice."""
        return cls(
            candidate_k=tunables.rag_candidate_k,
            rrf_k=tunables.rrf_k,
            context_k=tunables.rag_context_k,
            reranker=tunables.reranker,
        )


__all__ = [
    "RagConfig",
    "RAG_CANDIDATE_K",
    "RRF_K",
    "RAG_CONTEXT_K",
    "RERANKER",
]
