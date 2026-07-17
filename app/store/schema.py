"""Typed conversation-store row models (conversation-store capability).

Pydantic mirrors of the ``threads`` and ``turns`` rows created by migration
``0001``. These are read/write row shapes for the store; the producer/consumer
queue contract between the orchestrator and the store-writer is the frozen
``TurnRecord`` DTO in ``app/contracts/store.py``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.rag import RetrievalContext


class ThreadRow(BaseModel):
    """One ``threads`` row."""

    model_config = ConfigDict(extra="forbid")

    thread_id: str
    user_id: str  # Client ID
    platform: str | None = None
    page: str | None = None
    entry_surface: str | None = None
    model_version: str | None = None
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TurnRow(BaseModel):
    """One ``turns`` row (column-faithful)."""

    model_config = ConfigDict(extra="forbid")

    turn_id: str
    thread_id: str
    turn_number: int
    user_message: str | None = None
    assistant_message: str | None = None
    detected_intent: str | None = None
    extracted_params: dict | None = None
    tool_calls: list[dict] = Field(default_factory=list)
    retrieval_context: RetrievalContext = Field(default_factory=list)
    render_blocks: list[dict] = Field(default_factory=list)
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model_version: str | None = None
    created_at: datetime | None = None
