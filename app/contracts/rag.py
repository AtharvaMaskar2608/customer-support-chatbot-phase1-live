"""Shared RAG contract types (router-contract capability, D14).

The single frozen shapes used by rag-service, the orchestrator, the
conversation-store writer, and tracing — none of which import ``app/rag/``. The
canonical ``retrieval_context: list[str]`` shape lives here so it is defined once.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

#: Canonical retrieval-context shape, persisted by the store, put on tracing
#: retriever spans, and produced by RAG. A single ``list[str]`` definition.
RetrievalContext = list[str]


class RefusalReason(str, Enum):
    """Why a RAG answer refused to answer."""

    no_relevant_context = "no_relevant_context"
    out_of_scope = "out_of_scope"
    low_confidence = "low_confidence"
    investment_advice = "investment_advice"


class RetrievedChunk(BaseModel):
    """One retrieved-and-fused KB chunk."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    text: str
    source_id: str  # source / entry id
    vector_score: float
    fts_rank: float
    fused_score: float


class RagAnswer(BaseModel):
    """A grounded RAG answer with citations and an explicit refusal flag."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str
    citations: list[str] = Field(default_factory=list)  # RetrievedChunk ids
    refused: bool = False
    refusal_reason: RefusalReason | None = None
    retrieval_context: RetrievalContext = Field(default_factory=list)
