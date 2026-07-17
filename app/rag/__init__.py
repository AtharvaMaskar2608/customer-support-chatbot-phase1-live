"""Hybrid RAG service (rag-service capability).

Hybrid retrieval (vector + FTS + RRF) over the frozen ``qa_chunks`` KB plus
grounded, citation-bearing generation with refusal/escalation. Public entry
points ``respond`` / ``retrieve`` / ``answer`` and the ``search_kb`` tool body
live in ``app.rag.service``; the shared contract types are re-exported from
``app.rag.models``.
"""

from __future__ import annotations

from app.rag.models import (
    RagAnswer,
    RagError,
    RefusalReason,
    RetrievalContext,
    RetrievedChunk,
)
from app.rag.service import RagService, answer, respond, retrieve, search_kb

__all__ = [
    "RagAnswer",
    "RagError",
    "RefusalReason",
    "RetrievalContext",
    "RetrievedChunk",
    "RagService",
    "respond",
    "retrieve",
    "answer",
    "search_kb",
]
