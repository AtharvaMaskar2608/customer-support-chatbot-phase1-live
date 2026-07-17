"""Typed span ergonomics, thread stitching, and the manual llm-span path.

Thin wrappers over DeepEval's ``@observe`` so every consumer types its spans
identically instead of re-deriving decorator usage:

- ``agent_span`` / ``retriever_span`` / ``llm_span`` / ``tool_span`` — apply as
  ``@agent_span`` (bare) or ``@agent_span(metrics=[...])`` (parameterized);
  both forms work because these are ``functools.partial`` over ``observe`` with
  ``type=`` pre-bound, matching the frozen ``SpanType`` taxonomy.
- ``stitch_thread`` — the §6.4 multi-turn stitch: tag each per-turn trace with
  the shared ``thread_id`` (+ ``user_id`` and turn metadata) on the current
  trace so DeepEval groups the turns into one conversation.
- ``log_llm_span`` — the manual **Path B** fallback used when the installed
  DeepEval has no Anthropic auto-patch hook: read the Anthropic response
  ``usage`` and record model + token counts on the current ``llm`` span.

``observe``, ``update_current_span``, and ``update_current_trace`` are
re-exported so consumers import the whole tracing surface from ``app.tracing``.
"""

from __future__ import annotations

import functools
from typing import Any

from deepeval.tracing import (
    observe,
    update_current_span,
    update_current_trace,
    update_llm_span,
)

from app.contracts.tracing import SpanType

#: Typed span decorators (one per frozen ``SpanType``). Pre-bind ``type=`` so a
#: consumer writes ``@agent_span`` / ``@retriever_span`` etc. rather than
#: repeating ``observe(type="agent")`` at every call site.
agent_span = functools.partial(observe, type=SpanType.agent.value)
retriever_span = functools.partial(observe, type=SpanType.retriever.value)
llm_span = functools.partial(observe, type=SpanType.llm.value)
tool_span = functools.partial(observe, type=SpanType.tool.value)


def stitch_thread(
    thread_id: str,
    user_id: str,
    *,
    turn_number: int,
    model_version: str,
) -> None:
    """Stitch the current turn's trace into its conversation (§6.4).

    Sets ``thread_id`` and ``user_id`` on the current trace so DeepEval groups
    every turn sharing ``thread_id`` into one thread, and records the turn
    number + model version as queryable metadata. Conversation state stays the
    app's responsibility — DeepEval only observes.
    """
    update_current_trace(
        thread_id=thread_id,
        user_id=user_id,
        metadata={"turn_number": turn_number, "model_version": model_version},
        tags=["conversation"],
    )


def log_llm_span(response: Any, model: str) -> None:
    """Manual **Path B**: record model + token usage on the current ``llm`` span.

    Used when the installed DeepEval ``configure()`` exposes no Anthropic
    auto-patch hook. Reads the Anthropic response ``usage`` (``input_tokens`` /
    ``output_tokens``) and forwards it via ``update_llm_span``. Missing counts
    default to ``0`` rather than raising, so a malformed/streamed response never
    breaks the request path.
    """
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    update_llm_span(
        model=model,
        input_token_count=input_tokens,
        output_token_count=output_tokens,
    )


__all__ = [
    "agent_span",
    "retriever_span",
    "llm_span",
    "tool_span",
    "stitch_thread",
    "log_llm_span",
    "observe",
    "update_current_span",
    "update_current_trace",
]
