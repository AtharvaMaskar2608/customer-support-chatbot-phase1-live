"""RAG models — frozen contract re-exports plus the typed ``RagError``.

``RetrievedChunk`` / ``RagAnswer`` / ``RetrievalContext`` / ``RefusalReason`` are
the frozen ``contracts-foundation`` shapes (``app/contracts/rag.py``, design D14);
this module re-exports them so callers and tests import them from ``app.rag`` while
the single definition stays in the contract module. ``RagError`` is the one new
type this change defines: a typed failure the orchestrator maps to the shared
error taxonomy (E-TIMEOUT / E-UNKNOWN) — no user-facing copy is produced here.
"""

from __future__ import annotations

from typing import Literal

from app.contracts.rag import (
    RagAnswer,
    RefusalReason,
    RetrievalContext,
    RetrievedChunk,
)

#: The pipeline stage a RagError originated in, so the orchestrator can map it to
#: the right conversational error code (embedding/LLM/DB failure → E-TIMEOUT or
#: E-UNKNOWN per the shared taxonomy).
RagErrorStage = Literal["embedding", "db", "llm"]


class RagError(Exception):
    """A typed RAG pipeline failure (embedding / DB / LLM).

    Carries the failing ``stage`` and the underlying ``cause`` so the orchestrator
    maps it to the shared error taxonomy. Deliberately produces NO user-facing
    copy — rendering the conversational error bubble is the orchestrator's job.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: RagErrorStage,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.stage: RagErrorStage = stage
        self.cause = cause


__all__ = [
    "RagAnswer",
    "RefusalReason",
    "RetrievalContext",
    "RetrievedChunk",
    "RagError",
    "RagErrorStage",
]
