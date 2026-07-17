"""TurnRecord producer/consumer DTO (conversation-store capability, D14).

The single frozen shape the orchestrator enqueues (``enqueue(TurnRecord)`` after
each bot response) and the store-writer inserts. It mirrors the ``turns`` columns
of migration ``0001`` (plus ``user_id`` from ``threads``) one-to-one, so neither
side redefines the row. ``retrieval_context`` uses the canonical ``list[str]``
shape from ``app/contracts/rag.py``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.rag import RetrievalContext
from app.contracts.router import Intent

#: Maps each ``turns`` column (from migration 0001) to its TurnRecord field,
#: documenting the 1:1 correspondence (``detected_intent`` surfaces as ``intent``).
TURN_COLUMN_TO_FIELD: dict[str, str] = {
    "turn_id": "turn_id",
    "thread_id": "thread_id",
    "turn_number": "turn_number",
    "user_message": "user_message",
    "assistant_message": "assistant_message",
    "detected_intent": "intent",
    "extracted_params": "extracted_params",
    "tool_calls": "tool_calls",
    "retrieval_context": "retrieval_context",
    "render_blocks": "render_blocks",
    "latency_ms": "latency_ms",
    "prompt_tokens": "prompt_tokens",
    "completion_tokens": "completion_tokens",
    "model_version": "model_version",
    "created_at": "created_at",
}


class TurnRecord(BaseModel):
    """A completed turn, ready to persist. Frozen producer/consumer contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Identity (thread_id/user_id come from the threads row; turn_id/turn_number
    # from the turns row).
    thread_id: str
    turn_id: str
    user_id: str  # Client ID (threads.user_id)
    turn_number: int

    # Conversation content.
    user_message: str | None = None
    assistant_message: str | None = None

    # Decisions and tool traces (turns.detected_intent / extracted_params /
    # tool_calls / retrieval_context / render_blocks).
    intent: Intent | None = None
    extracted_params: dict | None = None
    tool_calls: list[dict] = Field(default_factory=list)  # name + args + results
    retrieval_context: RetrievalContext = Field(default_factory=list)
    render_blocks: list[dict] = Field(default_factory=list)

    # Usage + provenance.
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model_version: str | None = None
    created_at: datetime | None = None
