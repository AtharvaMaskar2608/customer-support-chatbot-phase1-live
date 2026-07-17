"""tracing-observability capability — concrete DeepEval wiring.

The implementation of the frozen ``tracing-conventions`` contract
(``app/contracts/tracing.py``): the global setup wrapper, the PII mask, typed
span helpers + thread stitching, the dual Anthropic auto-patch / manual
llm-span path, trace housekeeping, and the production no-local-judge guard.

Other packages import from here so span typing and PII redaction are wired
identically everywhere, rather than each re-deriving decorator usage.
"""

from __future__ import annotations

from app.tracing.mask import mask_pii
from app.tracing.spans import (
    agent_span,
    llm_span,
    log_llm_span,
    observe,
    retriever_span,
    stitch_thread,
    tool_span,
    update_current_span,
    update_current_trace,
)

__all__ = [
    # PII mask
    "mask_pii",
    # typed span helpers
    "agent_span",
    "retriever_span",
    "llm_span",
    "tool_span",
    # thread stitching + manual llm-span (Path B)
    "stitch_thread",
    "log_llm_span",
    # re-exported DeepEval primitives
    "observe",
    "update_current_span",
    "update_current_trace",
]
