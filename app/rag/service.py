"""Public RAG entry points (spec §5; contracts §Contracts & API structure).

``RagService`` wires the retriever and generator behind the three public
functions ``respond`` / ``retrieve`` / ``answer`` plus the ``search_kb`` native-
tool body. Dependencies (db / embedder / llm / config) are injected, so the
orchestrator and tests build it explicitly; the module-level ``respond`` /
``retrieve`` / ``answer`` / ``search_kb`` delegate to a lazily-constructed default
service (DSN from ``DATABASE_URL``) for production callers.

``respond`` attaches the real ``retrieval_context`` (canonical ``list[str]``) for
the store, tracing, and DeepEval, and threads the sticky-language decision from
``ConversationContext`` into generation.
"""

from __future__ import annotations

import os

from app.config.db import Database, make_engine
from app.contracts.router import ConversationContext
from app.contracts.tracing import MaskFn, default_mask
from app.llm.client import LLMClient
from app.rag.config import RAG_CONTEXT_K, RagConfig
from app.rag.embeddings import QueryEmbedder
from app.rag.generator import Generator
from app.rag.models import RagAnswer, RetrievedChunk
from app.rag.retriever import Retriever


class RagService:
    """Wires retrieval + grounded generation into the public RAG surface."""

    def __init__(
        self,
        db: Database,
        *,
        embedder: QueryEmbedder | None = None,
        llm: LLMClient | None = None,
        config: RagConfig | None = None,
        mask: MaskFn = default_mask,
    ) -> None:
        self.config = config or RagConfig()
        self.retriever = Retriever(
            db, embedder or QueryEmbedder(), self.config, mask=mask
        )
        self.generator = Generator(llm or LLMClient())

    async def retrieve(self, query: str, k: int | None = None) -> list[RetrievedChunk]:
        """Embed + vector/FTS search + RRF; return the top-``k`` fused chunks."""
        return await self.retriever.retrieve(query, k)

    def answer(
        self,
        query: str,
        context: list[RetrievedChunk],
        language=None,
    ) -> RagAnswer:
        """Grounded generation over ``context`` only; enforces refusal/escalation."""
        return self.generator.answer(query, context, language)

    async def respond(self, query: str, ctx: ConversationContext) -> RagAnswer:
        """Public entry: retrieve → answer, carrying the sticky-language decision.

        The returned ``RagAnswer`` already carries the real ``retrieval_context``.
        """
        context = await self.retrieve(query)
        return self.answer(query, context, ctx.detected_language)

    async def search_kb(self, query: str) -> list[RetrievedChunk]:
        """The ``search_kb`` native-tool body: run retrieval and return the fused
        chunks for the orchestrator to hand back as ``tool_result`` content."""
        return await self.retrieve(query)


# ---------------------------------------------------------------------------
# Module-level convenience API over a lazily-built default service.
# ---------------------------------------------------------------------------

_default_service: RagService | None = None


def _service() -> RagService:
    global _default_service
    if _default_service is None:
        dsn = os.environ["DATABASE_URL"]
        _default_service = RagService(make_engine(dsn))
    return _default_service


async def respond(query: str, ctx: ConversationContext) -> RagAnswer:
    """Retrieve → grounded answer for ``query`` in ``ctx`` (default service)."""
    return await _service().respond(query, ctx)


async def retrieve(query: str, k: int = RAG_CONTEXT_K) -> list[RetrievedChunk]:
    """Hybrid retrieval for ``query``, top-``k`` fused chunks (default service)."""
    return await _service().retrieve(query, k)


def answer(query: str, context: list[RetrievedChunk]) -> RagAnswer:
    """Grounded generation over ``context`` only (default service)."""
    return _service().answer(query, context)


async def search_kb(query: str) -> list[RetrievedChunk]:
    """The ``search_kb`` tool body over the default service."""
    return await _service().search_kb(query)


def tool_result_text(chunks: list[RetrievedChunk]) -> str:
    """Format fused chunks as ``search_kb`` ``tool_result`` text for the agent loop."""
    if not chunks:
        return "No knowledge-base entries matched."
    return "\n\n".join(f"[id: {c.chunk_id}]\n{c.text}" for c in chunks)


__all__ = [
    "RagService",
    "respond",
    "retrieve",
    "answer",
    "search_kb",
    "tool_result_text",
]
