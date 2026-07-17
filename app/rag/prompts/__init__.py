"""RAG generation prompts (rag-service capability).

The grounded-answer system prompt + refusal rules and the context-formatting
builder. Kept under ``app/rag/prompts`` (RAG owns these) rather than
``app/llm/prompts`` (llm-router's). See ``grounded.py``.
"""

from __future__ import annotations

from app.rag.prompts.grounded import (
    GROUNDED_SYSTEM_PROMPT,
    build_system_prompt,
    build_user_message,
)

__all__ = [
    "GROUNDED_SYSTEM_PROMPT",
    "build_system_prompt",
    "build_user_message",
]
